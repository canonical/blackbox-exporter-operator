"""Docstring for blackbox-exporter-operator.src.utils.

This utils module will hold ops-independent logic to be used by charm code.
"""
import subprocess
from dataclasses import dataclass
from ipaddress import IPv4Interface, IPv4Network
from pathlib import Path
from typing import cast

from netifaces import AF_INET, InterfaceType, ifaddresses, interfaces


@dataclass(frozen=True)
class Network:
    """Represents an IPv4 network bound to a system network interface.

    Attributes:
        iface (str): Name of the network interface (e.g. "lo", "eth0").
        ip (str): IPv4 address assigned to the interface.
        net (IPv4Network): IPv4 network derived from the IP and netmask.
    """
    iface: str
    ip: str
    net: IPv4Network

    def to_dict(self) -> dict[str, str]:
        """Convert the Network object into a JSON-serializable dictionary.

        Returns:
            dict[str, str]: A dictionary with keys:
                - "iface": interface name
                - "ip": IPv4 address as a string
                - "net": IPv4 network in CIDR notation
        """
        return {
            "iface": self.iface,
            "ip": self.ip,
            "net": str(self.net),
        }


def get_unit_networks() -> list[Network]:
    """Return all IP addresses of the machine hosting this unit across all interfaces."""
    networks: list[Network] = []

    for iface in filter(lambda iface: iface not in {"lo"}, interfaces()):
        addrs = ifaddresses(iface).get(cast(InterfaceType, AF_INET), [])

        for addr in addrs:
            addr = cast(dict[str, str], addr)

            ip = addr.get("addr")
            netmask = addr.get("netmask")

            if not ip:
                continue

            # If no netmask, assume /32
            iface_ip = (
                IPv4Interface(f"{ip}/{netmask}")
                if netmask
                else IPv4Interface(f"{ip}/32")
            )

            networks.append(
                Network(
                    iface=iface,
                    ip=str(iface_ip.ip),
                    net=iface_ip.network,
                )
            )

    return networks

def is_snap_active(snap_name: str) -> bool:
    """Return True if the snap is installed and in the 'active' state."""
    try:
        # snap services returns the status of the service
        result = subprocess.run(
            ["snap", "services", snap_name],
            capture_output=True,
            text=True,
            check=True,
        )
        # Output example:
        # Service                 Startup  Current  Notes
        # prometheus-blackbox-exporter.enable  enabled  active   -
        # We check for 'active' in the Current column
        for line in result.stdout.splitlines():
            if snap_name in line:
                if "active" in line.split():
                    return True
        return False
    except subprocess.CalledProcessError:
        return False

def file_contents(path: Path) -> str | None:
    """Return the content of a file at path `path`."""
    if not path.exists():
        return None
    return path.read_text()
