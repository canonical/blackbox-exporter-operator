#!/usr/bin/env python3
# Copyright 2026 Ltd.
# See LICENSE file for licensing details.

"""Charm the Blackbox Exporter."""

import json
import logging
import socket
from pathlib import Path
from typing import Any, Dict, List, Tuple, TypedDict, cast

import ops
import yaml
from charms.grafana_agent.v0.cos_agent import COSAgentProvider
from charms.operator_libs_linux.v2 import snap
from cosl.reconciler import all_events, observe_events
from ops import CollectStatusEvent, StoredState
from ops.jujucontext import JujuContext
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, StatusBase

from constants import (
    COS_AGENT_RELATION_NAME,
    DEFAULT_PORT,
    LOG_SLOT_NAME,
    PEERS_RELATION_NAME,
    SNAP_CONFIG_LOCATION,
    SNAP_NAME,
)
from singleton_snap import SingletonSnapManager
from snap_management import (
    SnapMap,
    SnapServiceError,
    SnapSpecError,
    install_snap,
)
from utils import file_contents, get_unit_networks, is_snap_active

logger = logging.getLogger(__name__)

SNAP_CONFIG_PATH = Path(SNAP_CONFIG_LOCATION)

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
    snap: Tuple[str, str]

    # For the validation of config.
    config: Tuple[str, str]


def to_tuple(status: StatusBase) -> Tuple[str, str]:
    """Convert a StatusBase to tuple, so it is marshallable into StoredState."""
    return status.name, status.message

def to_status(tpl: Tuple[str, str]) -> StatusBase:
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
                config=to_tuple(ActiveStatus())
            )
        )

        if event() in ("install", "upgrade"):
            config_status_success = self._push_config()
            if config_status_success:
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
            scrape_configs=self._self_metrics,
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
        config_status_success = self._push_config()
        if config_status_success:
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
        if file_contents(SNAP_CONFIG_PATH) == config:
            return False

        # If the config_file is empty, the default config provided by the snap will be used.
        if not config:
            return True

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

        # Now we validate that it is a dict with a 'modules' section
        if not isinstance(provided_config, dict) or "modules" not in provided_config:
            logger.error(
                "Config is valid YAML but missing top-level `modules` section."
            )
            self._stored.status["config"] = to_tuple(
                BlockedStatus("Config file is invalid; see debug-log")
            )
            return False

        # If the file is valid YAML, then we overwrite the default snap config.
        # If we get to this point in the code, the config is guaranteed to at least
        # be valid YAML.
        SNAP_CONFIG_PATH.write_text(config)
        logger.info(f"Overwrote the config for the snap at {SNAP_CONFIG_LOCATION}")
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
                logger.info(f"Installing snap {snap_name}")

                self._stored.status["snap"] = to_tuple(
                    MaintenanceStatus(f"Installing snap {snap_name}")
                    )
                install_snap(snap_name)

                self._stored.status["snap"] = to_tuple(
                    MaintenanceStatus(f"Starting snap {snap_name}")
                    )
                try:
                    logger.info(f"Starting {snap_name} snap")
                    self.snap(snap_name).start(enable=True)
                    self._stored.status["snap"] = to_tuple(ActiveStatus())
                except snap.SnapError as e:
                    self._stored.status["snap"] = to_tuple(
                        BlockedStatus("Unable to install the snap; see debug-log")
                        )
                    logger.warn(f"Failed to start snap {snap_name}")
                    raise SnapServiceError(f"Failed to start {snap_name}") from e

    def _restart_snap(self, snap_name: str) -> None:
        try:
            logger.info(f"Restarting snap {snap_name}")
            self.snap(snap_name).restart()
        except snap.SnapError as e:
            logger.warning(f"Failed to restart prometheus-blackbox-exporter snap: {e}")

    def _remove_blackbox_exporter(self):
        """Coordinate blackbox-exporter snap and config file removal."""
        self._stored.status["snap"] = to_tuple(
            MaintenanceStatus("Removing Blackbox Exporter")
        )
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
        self._stored.status["snap"] = to_tuple(
            MaintenanceStatus(f"Uninstalling {snap_name} snap")
        )
        try:
            self.snap(snap_name).ensure(state=snap.SnapState.Absent)
            logger.info(f"{snap_name} snap was uninstalled")
        except (snap.SnapError, SnapSpecError) as e:
            # Log error but don't fail the remove hook - this is common in test environments
            logger.error(f"Failed to uninstall {snap_name} snap: {e}")
            # Don't raise the exception to avoid failing the remove hook

    def _update_peer_relation_data(self):
        if not self.model.get_relation(PEERS_RELATION_NAME):
            return
        peer_relation_data = {
            "principal-unit": juju_context("principal_unit") or "",
            "principal-hostname": socket.gethostname(),
            "unit-networks": json.dumps([n.to_dict() for n in get_unit_networks()]),
            "az": juju_context("availability_zone") or "",
        }
        relation = self.model.get_relation(PEERS_RELATION_NAME)
        assert relation is not None

        relation.data[self.unit].update(peer_relation_data)

    def _generate_scrape_jobs(self):
        """Scrape jobs from peer relation data will be generated by this method."""
        pass

    @property
    def _self_metrics(self) -> List[Dict[str, Any]]:
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

        return [job]

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
