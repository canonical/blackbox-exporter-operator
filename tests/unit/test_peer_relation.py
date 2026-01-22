# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
#
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import pytest
from ops import testing

from charm import BlackboxExporterOperatorCharm
from scenario import Context, PeerRelation, Relation, State
import json
import logging

logger = logging.getLogger(__name__)

def test_peer_relation_data(context):
    # GIVEN BE peers.
    peer_relation = PeerRelation(endpoint="peers", peers_data={1: {}, 2: {}, 3: {}})
    state = State(relations={peer_relation})
    logger.info(state)
    # WHEN any event executes the reconciler
    with context(context.on.update_status(), state=state) as mgr:
        state_out = mgr.run()
        logger.info(state_out)
        remote_write_relation = next((obj for obj in state_out.relations if obj.endpoint == "send-remote-write"), None)

        remote_write_relation_json = json.loads(getattr(remote_write_relation, "local_app_data", {}).get("alert_rules", {}))
        assert remote_write_relation_json