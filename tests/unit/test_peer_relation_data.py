# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
#
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/


import json
import logging

from scenario import PeerRelation, State

logger = logging.getLogger(__name__)

mock_ports = [80, 443]


def test_peer_relation_data(context):
    # GIVEN a BE with peers.
    peer_relation = PeerRelation(endpoint="peers", peers_data={1: {}})
    state = State(relations={peer_relation})
    # WHEN any event executes the reconciler.
    with (
        context(context.on.relation_joined(peer_relation), state=state) as mgr,
    ):
        state_out = mgr.run()

        peer_relation = next((obj for obj in state_out.relations if obj.endpoint == "peers"), None)

        unit_networks_data = json.loads(
            getattr(peer_relation, "local_unit_data", {}).get("unit-networks", [])
        )

        # THEN the unit's networks' data must be written to remote unit data.
        assert unit_networks_data

        # AND inside that unit networks data, there must be the iface, ip, and net and other keys
        required_keys = ["iface", "ip", "net"]
        for interface in unit_networks_data:
            assert all(interface.get(k) for k in required_keys)
