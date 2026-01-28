from ipaddress import IPv4Network

import netifaces

from src.utils import Network, get_unit_networks

"""
This file tests the get_unit_networks function and Network class
defined in utils.py
The tests here are intentionally scenario-independent, as
the utils module itself is.
"""
def test_loopback_interface_is_ignored(monkeypatch):
    monkeypatch.setattr(
        "src.utils.interfaces",
        lambda: ["lo"]
    )

    monkeypatch.setattr(
        "src.utils.ifaddresses",
        lambda iface: {
            netifaces.AF_INET: [
                {
                    "addr": "127.0.0.1",
                    "netmask": "255.0.0.0",
                }
            ]
        }
    )

    networks = get_unit_networks()

    assert networks == []

def test_single_interface(monkeypatch):
    monkeypatch.setattr(
        "src.utils.interfaces",
        lambda: ["eth0"]
    )

    monkeypatch.setattr(
        "src.utils.ifaddresses",
        lambda iface: {
            netifaces.AF_INET: [
                {
                    "addr": "192.168.1.10",
                    "netmask": "255.255.255.0",
                }
            ]
        }
    )

    networks = get_unit_networks()

    assert networks == [
        Network(
            iface="eth0",
            ip="192.168.1.10",
            net=IPv4Network("192.168.1.0/24"),
        )
    ]

def test_multiple_interfaces(monkeypatch):
    monkeypatch.setattr(
        "src.utils.interfaces",
        lambda: ["eth0", "wlan0"]
    )

    def fake_ifaddresses(iface):
        if iface == "eth0":
            return {
                netifaces.AF_INET: [
                    {"addr": "192.168.1.2", "netmask": "255.255.255.0"}
                ]
            }
        if iface == "wlan0":
            return {
                netifaces.AF_INET: [
                    {"addr": "10.0.0.5", "netmask": "255.255.255.0"}
                ]
            }
        return {}

    monkeypatch.setattr(
        "src.utils.ifaddresses",
        fake_ifaddresses
    )

    networks = get_unit_networks()

    assert networks == [
        Network(
            iface="eth0",
            ip="192.168.1.2",
            net=IPv4Network("192.168.1.0/24"),
        ),
        Network(
            iface="wlan0",
            ip="10.0.0.5",
            net=IPv4Network("10.0.0.0/24"),
        ),
    ]
