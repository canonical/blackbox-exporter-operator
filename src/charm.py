#!/usr/bin/env python3
# Copyright 2026 Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import json
import logging
import os
import socket
import subprocess
import sys
from ipaddress import IPv4Interface
from typing import cast

import ops
from charms.operator_libs_linux.v2 import snap
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from netifaces import AF_INET, InterfaceType, ifaddresses, interfaces
from ops.model import ActiveStatus, MaintenanceStatus

from constants import PEERS_RELATION_NAME, PROBES_RELATION_NAME
from singleton_snap import SingletonSnapManager
from snap_management import (
    SnapMap,
    SnapServiceError,
    SnapSpecError,
    install_snap,
)

logger = logging.getLogger(__name__)


def event() -> str:
    """Return Juju hook|action name.

    Refs:
    - https://github.com/juju/juju/blob/cbb05654c7444dd6bee29e49aff16339f02c34f9/docs/reference/action.md?plain=1#L55
    - https://github.com/juju/juju/blob/cbb05654c7444dd6bee29e49aff16339f02c34f9/docs/reference/hook.md?plain=1#L1088
    """
    return os.environ.get("JUJU_HOOK_NAME") or os.environ.get("JUJU_ACTION_NAME", "")


def principal_unit():
    """Return the principal unit of this unit, otherwise None."""
    # Juju 2.2 and above provides JUJU_PRINCIPAL_UNIT
    return os.environ.get("JUJU_PRINCIPAL_UNIT", None)


def get_az():
    """Return the Juju Availability Zones."""
    az = os.getenv("JUJU_AVAILABILITY_ZONE") or "None"
    return az


def get_unit_networks():
    """Return all IP addresses of the machine hosting this unit across all interfaces."""
    networks = []

    for iface in interfaces():
        if iface == "lo":
            continue

        addrs = ifaddresses(iface).get(cast(InterfaceType, AF_INET), [])

        for addr in addrs:
            addr = cast(dict[str, str], addr)

            ip = addr.get("addr")
            netmask = addr.get("netmask")

            if not ip:
                continue

            # If no netmask, assume /32
            if netmask:
                iface_ip = IPv4Interface(f"{ip}/{netmask}")
            else:
                iface_ip = IPv4Interface(f"{ip}/32")

            networks.append(
                {
                    "iface": iface,
                    "ip": str(iface_ip.ip),
                    "net": str(iface_ip.network),
                }
            )

    return networks


def get_principal_unit_open_ports():
    """Return the open ports on the machine hosting this unit."""
    cmd = "lsof -P -iTCP -sTCP:LISTEN".split()
    result = subprocess.check_output(cmd)
    result = result.decode(sys.stdout.encoding)

    ports = []
    for r in result.split("\n"):
        for p in r.split():
            if "*:" in p:
                ports.append(p.split(":")[1])
    ports = list(set(ports))

    return ports


class BlackboxExporterOperatorCharm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        logger.info("Event is %s", event)
        if event() in ("install", "upgrade"):
            self._install_snaps()
        elif event() == "remove":
            self._remove_blackbox_exporter()
            return

        self._reconcile()

    def _reconcile(self):
        self._scraping = MetricsEndpointProvider(
            self,
            relation_name=PROBES_RELATION_NAME,
            # TODO: this needs to be equal to the jobs specified by _generate_scrape_jobs
            # and the probes_file config option (to be added)
            jobs=[],
            refresh_event=[
                self.on.config_changed,
                self.on.update_status,
            ],
        )

        self._update_peer_relation_data()
        self.unit.status = ActiveStatus()

    def snap(self, snap_name: str) -> snap.Snap:
        """Return the snap object for the given snap.

        This method provides lazy initialization of snap objects, avoiding unnecessary
        calls to snapd until they're actually needed.
        """
        return snap.SnapCache()[snap_name]

    def _install_snaps(self) -> None:
        manager = SingletonSnapManager(self.unit.name)

        for snap_name in SnapMap.snaps():
            snap_revision = SnapMap.get_revision(snap_name)
            manager.register(snap_name, snap_revision)
            revisions = manager.get_revisions(snap_name)
            if snap_revision >= (max(revisions) if revisions else 0):
                # Install the snap
                self.unit.status = MaintenanceStatus(f"Installing {snap_name} snap")
                install_snap(snap_name)
                # Start the snap
                self.unit.status = MaintenanceStatus(f"Starting {snap_name} snap")
                try:
                    self.snap(snap_name).start(enable=True)
                except snap.SnapError as e:
                    raise SnapServiceError(f"Failed to start {snap_name}") from e

    def _remove_blackbox_exporter(self):
        """Coordinate blackbox-exporter snap and config file removal."""
        self.unit.status = MaintenanceStatus("sdgsgsdsdg")
        manager = SingletonSnapManager(self.unit.name)
        snap_name = "prometheus-blackbox-exporter"
        snap_revision = SnapMap.get_revision(snap_name)
        manager.unregister(snap_name, snap_revision)
        logger.info(
            "Is manager in use by other units? %s", manager.is_used_by_other_units(snap_name)
        )
        if manager.is_used_by_other_units(snap_name):
            try:
                self.snap(snap_name).restart()
            except snap.SnapError as e:
                logger.warning(f"Failed to restart prometheus-blackbox-exporter snap: {e}")
        else:
            try:
                self._remove_snap(snap_name)
                logger.info("Removed the prometheus-blackbox-exporter snap")
            except Exception as e:
                logger.warning(f"Unable to remove the prometheus-blackbox-exporter snap: {e}")

    def _remove_snap(self, snap_name: str):
        """Attempt to remove the snap."""
        self.unit.status = MaintenanceStatus(f"Uninstalling {snap_name} snap")
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
        self.unit.status = MaintenanceStatus("Updating peer relation data")
        peer_relation_data = {
            "principal-unit": self.model.unit.name if self.model.unit else "",
            "principal-hostname": socket.gethostname(),
            "unit-networks": json.dumps(get_unit_networks()),
            "az": get_az() or "",
            "unit-ports": json.dumps(get_principal_unit_open_ports() or []),
        }
        relation = self.model.get_relation(PEERS_RELATION_NAME)
        assert relation is not None

        relation.data[self.unit].update(peer_relation_data)

        self.unit.status = ActiveStatus()

    def _generate_scrape_jobs(self):
        """Scrape jobs from peer relation data will be generated by this method."""
        pass


if __name__ == "__main__":  # pragma: nocover
    ops.main(BlackboxExporterOperatorCharm)
