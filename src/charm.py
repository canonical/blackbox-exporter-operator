#!/usr/bin/env python3
# Copyright 2026 Ltd.
# See LICENSE file for licensing details.

"""A charmed operator for Blackbox Exporter."""

import json
import logging
import socket
from typing import Any, Dict, List, TypedDict, cast

import ops
import yaml
from charms.grafana_agent.v0.cos_agent import COSAgentProvider
from charms.operator_libs_linux.v2 import snap
from cosl.reconciler import all_events, observe_events
from ops import CollectStatusEvent, Relation, StoredState
from ops.jujucontext import JujuContext
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, StatusBase
from pydantic import ValidationError

from constants import (
    COS_AGENT_RELATION_NAME,
    DEFAULT_CONFIG_FILE,
    DEFAULT_PORT,
    LOG_SLOT_NAME,
    PEERS_RELATION_NAME,
    SNAP_CONFIG_PATH,
    SNAP_NAME,
)
from models import Config, ProbesFile
from singleton_snap import SingletonSnapManager
from snap_management import (
    SnapMap,
    SnapSpecError,
    install_snap,
)
from utils import file_contents, get_unit_networks, is_snap_active

logger = logging.getLogger(__name__)

PRINCIPAL_HOSTNAME = socket.gethostname()

def juju_context(arg: str):
    """Return Juju env variables."""
    return getattr(JujuContext.from_environ(), arg)

def event() -> str:
    """Return Juju hook|action name.

    Refs:
    - https://github.com/juju/juju/blob/cbb05654c7444dd6bee29e49aff16339f02c34f9/docs/reference/action.md?plain=1#L55
    - https://github.com/juju/juju/blob/cbb05654c7444dd6bee29e49aff16339f02c34f9/docs/reference/hook.md?plain=1#L1088
    """
    return juju_context("hook_name")

class CompositeStatus(TypedDict):
    """Per-component status holder."""

    # For the status of snap installation, start.
    snap: tuple[str, str]

    # For the validation of config.
    config: tuple[str, str]

    # For the validation of the probes file.
    probes_file: tuple[str, str]


def to_tuple(status: StatusBase) -> tuple[str, str]:
    """Convert a StatusBase to tuple, so it is marshallable into StoredState."""
    return status.name, status.message

def to_status(tpl: tuple[str, str]) -> StatusBase:
    """Convert a tuple to a StatusBase, so it could be used natively with ops."""
    name, message = tpl
    return StatusBase.from_name(name, message)


class BlackboxExporterOperatorCharm(ops.CharmBase):
    """Charm the application."""

    _stored = StoredState()

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)

        self._stored.set_default(
            status=CompositeStatus(
                snap=to_tuple(ActiveStatus()),
                config=to_tuple(ActiveStatus()),
                probes_file=to_tuple(ActiveStatus()),
            )
        )

        if event() in ("install", "upgrade"):
            self._install_snaps()

        elif event() == "remove":
            self._remove_blackbox_exporter()
            return

        self.cos_agent_provider = COSAgentProvider(
            self,
            relation_name=COS_AGENT_RELATION_NAME,
            # TODO: this needs to be equal to the jobs specified by _generate_scrape_jobs
            # and the probes_file config option (to be added)
            # and the self metrics endpoint
            scrape_configs=self._all_scrape_jobs,
            log_slots=[f"{SNAP_NAME}:{LOG_SLOT_NAME}"],
            refresh_events=[
                self.on.config_changed,
                self.on.update_status,
            ],
        )

        self.framework.observe(self.on.collect_unit_status, self._collect_unit_status)
        observe_events(self, all_events, self._reconcile)

    def _collect_unit_status(self, event: CollectStatusEvent):
        # Push status
        for status in self._stored.status.values():
            event.add_status(to_status(status))

        # Pull status
        if not is_snap_active(SNAP_NAME):
            event.add_status(BlockedStatus(f"Snap {SNAP_NAME} is inactive; see debug-log"))

    def _reconcile(self):
        if self._push_config():
            self._restart_snap(SNAP_NAME)

        if event() == "peers-relation-joined":
            self._update_peer_relation_data()

    def snap(self, snap_name: str) -> snap.Snap:
        """Return the snap object for the given snap.

        This method provides lazy initialization of snap objects, avoiding unnecessary
        calls to snapd until they're actually needed.
        """
        return snap.SnapCache()[snap_name]

    def _push_config(self) -> bool:
        """Validate provided config and overwrite current snap config.

        Return True if the config is overwritten.
        Return False otherwise e.g. when the new config is invalid.
        """
        config = cast(str, self.model.config.get("config_file"))

        # If config hasn't changed, return False as no overwriting will happen.
        # Or if the juju config option is None and we are already using the default,
        #return False
        current_config = file_contents(SNAP_CONFIG_PATH)
        if current_config == config or (current_config == DEFAULT_CONFIG_FILE and not config):
            return False

        # If the config_file is empty, the default will be used.
        if not config:
            config = DEFAULT_CONFIG_FILE

        # We do a basic config validation of the yaml content
        try:
            provided_config = yaml.safe_load(config)

        # Only catching yaml.YamlError or yaml.scanner.ScannerError
        # may not be very robust. Let's assume the generic Exception is
        # due to invalid YAML.
        except Exception as e:
            logger.error("Failed to load the configuration; invalid YAML: %s %s", config, str(e))
            self._stored.status["config"] = to_tuple(
                BlockedStatus("Config file is invalid; see debug-log")
            )
            return False

        # Now we validate the config with the Config BaseModel.
        try:
            Config(**provided_config)
        except Exception as e:
            logger.error("Config validation failed: %s", e)
            self._stored.status["config"] = to_tuple(
                BlockedStatus("Config file is invalid; see debug-log")
            )
            return False

        # If the file is valid YAML, then we overwrite the default snap config.
        # If we get to this point in the code, the config is guaranteed to at least
        # be valid YAML.
        SNAP_CONFIG_PATH.write_text(config)
        logger.info(f"Overwrote config for the Blackbox Exporter snap at {SNAP_CONFIG_PATH}")
        self._stored.status["config"] = to_tuple(
                    ActiveStatus()
                    )
        return True

    def _install_snaps(self) -> None:
        manager = SingletonSnapManager(self.unit.name)

        for snap_name in SnapMap.snaps():

            snap_revision = SnapMap.get_revision(snap_name)
            manager.register(snap_name, snap_revision)
            revisions = manager.get_revisions(snap_name)
            if snap_revision >= (max(revisions) if revisions else 0):
                logger.info("Installing snap {snap_name}")

                self.unit.status = MaintenanceStatus(f"Installing snap {snap_name}")

                install_snap(snap_name)

                self.unit.status = MaintenanceStatus(f"Starting snap {snap_name}")

                try:
                    logger.info(f"Starting {snap_name} snap")
                    self.snap(snap_name).start(enable=True)
                    self._stored.status["snap"] = to_tuple(ActiveStatus())
                except snap.SnapError:
                    logger.warning(f"Failed to start snap {snap_name}")

    def _restart_snap(self, snap_name: str) -> None:
        try:
            logger.info(f"Restarting snap {snap_name}")
            self.snap(snap_name).restart()
        except snap.SnapError as e:
            logger.warning(f"Failed to restart prometheus-blackbox-exporter snap: {e}")

    def _remove_blackbox_exporter(self):
        """Coordinate blackbox-exporter snap and config file removal."""
        self.unit.status = MaintenanceStatus("Removing Blackbox Exporter")

        manager = SingletonSnapManager(self.unit.name)
        snap_revision = SnapMap.get_revision(SNAP_NAME)
        manager.unregister(SNAP_NAME, snap_revision)

        if manager.is_used_by_other_units(SNAP_NAME):
            self._restart_snap(SNAP_NAME)
        else:
            try:
                self._remove_snap(SNAP_NAME)
                logger.info("Removed the prometheus-blackbox-exporter snap")
            except Exception as e:
                logger.warning(f"Unable to remove the prometheus-blackbox-exporter snap: {e}")

    def _remove_snap(self, snap_name: str):
        """Attempt to remove the snap."""
        self.unit.status = MaintenanceStatus(f"Uninstalling {snap_name} snap")
        try:
            self.snap(snap_name).ensure(state=snap.SnapState.Absent)
            logger.info(f"{snap_name} snap was uninstalled")
        except (snap.SnapError, SnapSpecError):
            # Log error but don't fail the remove hook - this is common in test environments
            logger.error("Failed to uninstall {snap_name} snap: {e}")
            # Don't raise the exception to avoid failing the remove hook

    def _update_peer_relation_data(self):
        if not self.model.get_relation(PEERS_RELATION_NAME):
            return
        peer_relation_data = {
            "principal-unit": juju_context("principal_unit") or "",
            "principal-hostname": PRINCIPAL_HOSTNAME,
            "unit-networks": json.dumps([n.to_dict() for n in get_unit_networks()]),
            "az": juju_context("availability_zone") or "",
        }
        relation = self.model.get_relation(PEERS_RELATION_NAME)
        assert relation is not None

        relation.data[self.unit].update(peer_relation_data)

    def _connectivity_scrape_jobs(self, relation: Relation) -> Dict[str, Any]:
        """Scrape jobs from peer relation data will be generated by this method."""
        scrape_job = {}
        scrape_job["job_name"] = f"{PRINCIPAL_HOSTNAME}-connectivity-checks"
        scrape_job["metrics_path"] = "/probe"

        # For basic connectivity, the ICMP module will suffice.
        scrape_job["params"] = {'module': ['icmp']}
        # This can be potentially exposed to the user via `juju config`
        scrape_job["scrape_interval"] = "60s"

        # Each peer has at least one network interface.
        # Static configs must have a `target` block per each peer and network address combination.
        # Therefore, the number of targets in static configs must be equal to
        # the number of peers * the number of interfaces per each peer
        # Targets can only be merged if they share the same labels.
        # There are no two peers which will share the same `interface` and `target` key,
        # so all targets must be separate dicts in static_configs.
        scrape_job["static_configs"] = []

        for unit in relation.units:
            rel_data = relation.data[unit]
            unit_networks = json.loads(rel_data.get("unit-networks", "[]"))

            if not unit_networks:
                continue

            for network in unit_networks:
                scrape_job["static_configs"].append({
                    'targets': [network["ip"]],
                    'labels': {
                        'interface': network['iface'],
                        'source': juju_context("principal_unit"),
                        'source_hostname': PRINCIPAL_HOSTNAME,
                        'destination': rel_data['principal-unit'],
                        'destination_hostname': rel_data['principal-hostname'],
                        'source_az': juju_context("availability_zone"),
                        'destination_az': rel_data['az'],
                        'probe': 'icmp'
                    }
                }
                )

        scrape_job['relabel_configs'] = [
                {'source_labels': ['__address__'], 'target_label': '__param_target'},
                {'source_labels': ['__param_target'], 'target_label': 'instance'},
                {'target_label': '__address__', 'replacement': self._machine_ip+':9115'}
            ]

        return scrape_job

    def _self_metrics(self) -> Dict[str, Any]:
        """Return the self-monitoring scrape job.

        It is expected that the scraping of this BE's self workload metrics
        will be done by an Otelcol that is on the same machine as
        this BE unit.

        Hence, the target can be <network-bind-address>:9115/metrics.
        """
        target = (
            f"{self._machine_ip}:{DEFAULT_PORT}"
        )

        # For self monitoring metrics, we'll rely on
        # labels coming from juju topology
        job = {
            "job_name": "be-self-monitoring",
            "metrics_path": "/metrics",
            "static_configs": [
                {
                    "targets": [target]
                }
            ],
            "scrape_timeout": "10s"
        }

        return job

    def _custom_scrape_jobs(self, probes_file: str) -> List[Dict[str, Any]]:
        """Validate and return a list of custom jobs."""
        try:
            probes_yaml = yaml.safe_load(probes_file)
        except Exception as e:
            logger.warning(
                "An error has occurred while validating the probes file using YAML %s", e
                )
            self._stored.status["probes_file"] = to_tuple(
                BlockedStatus("Error when validating probes file; see debug-log")
                )
            return []
        try:
            ProbesFile(**probes_yaml)
        except ValidationError as e:
            logger.warning("An error has occurred while validating the probes file %s", e)
            self._stored.status["probes_file"] = to_tuple(
                BlockedStatus("Invalid probes file; see debug-log")
            )
            return []
        extra_labels = {
            'source': juju_context("principal_unit"),
            'source_hostname': PRINCIPAL_HOSTNAME,
            }
        custom_jobs = probes_yaml["scrape_configs"]
        for job in custom_jobs:
            # Prepend the principal hostname to job_name
            job["job_name"] = f"{PRINCIPAL_HOSTNAME}-{job['job_name']}"

            # Add the source (principal_unit) and source hostname labels.
            # This will overwrite the value for these keys if they are provided.
            for static_config in job.get("static_configs", []):
                if "labels" not in static_config:
                    static_config["labels"] = {}
                static_config["labels"].update(extra_labels)
        logger.info("Custom scraped jobs have been validated and sanitized.")
        self._stored.status["probes_file"] = to_tuple(ActiveStatus())
        return custom_jobs

    @property
    def _all_scrape_jobs(self) -> List[Dict[str, Any]]:
        """Generate all scrape jobs defined by charm, to be scraped by a scraper.

        `All` scrape jobs consist of three different jobs:
        1. This charm's own self metrics monitoring. Returned by self._self_metrics()
        2. Scrape jobs that test connectivity between the machines hosting
            this BE charm and its peers. Returned by self._connectivity_scrape_jobs.
            These jobs will only be generated if
                a. there is more than 1 unit of BE AND
                b. automatic connectivity checks are enabled via Juju config options.
                    Currently, such a config option is not provided.
                    When it is, automatic connectivity checks are enabled by default.
        3. Any scrape jobs provided by the user via the `probes_file`
          config option. To be implemented.
        """
        all_scrape_jobs = []

        # Add self monitoring scrape jobs.
        all_scrape_jobs.append(self._self_metrics())

        # If there is more than 1 peer for this charm
        # AND automatic connectivity checks are enabled (config option to be added)
        # generate connectivity scrape jobs.
        peer_relation = self.model.get_relation(PEERS_RELATION_NAME)

        if peer_relation: # TODO AND auto connectivity checks enabled
            all_scrape_jobs.append(
                self._connectivity_scrape_jobs(peer_relation)
                )

        probes_file = cast(str, self.model.config.get("probes_file"))
        if probes_file:
            # all_scrape_jobs returns a list of jobs so we extend.
            all_scrape_jobs.extend(
                self._custom_scrape_jobs(probes_file)
            )

        return all_scrape_jobs

    @property
    def _machine_ip(self) -> str:
        """Return the bind address used for Juju for this machine.

        This is safe, even on a machine with multiple interfaces.
        """
        binding = self.model.get_binding("juju-info")
        assert binding is not None
        return str(binding.network.bind_address)


if __name__ == "__main__":  # pragma: nocover
    ops.main(BlackboxExporterOperatorCharm)
