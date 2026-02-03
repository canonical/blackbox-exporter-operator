"""Charm constants, for better testability."""

from pathlib import Path
from typing import Final

COS_AGENT_RELATION_NAME: Final[str] = "cos-agent"
PEERS_RELATION_NAME: Final[str] = "peers"
DEFAULT_PORT: Final[int] = 9115
LOG_SLOT_NAME: Final[str] = "prometheus-blackbox-exporter-logs"
SNAP_NAME: Final[str] = "prometheus-blackbox-exporter"
SNAP_CONFIG_PATH: Final[Path] = Path("/var/snap/prometheus-blackbox-exporter/current/blackbox.yml")
DEFAULT_CONFIG_FILE: Final[str] = """
modules:
    http_2xx:
        prober: http
        timeout: 10s
    tcp_connect:
        prober: tcp
        timeout: 10s
    icmp:
        prober: icmp
        timeout: 10s
        icmp:
            preferred_ip_protocol: "ip4"
            ip_protocol_fallback: true
"""
