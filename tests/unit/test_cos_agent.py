# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
#
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/


import json
import logging

from scenario import State, SubordinateRelation

logger = logging.getLogger(__name__)

def mock_get_version():
    """Get a mock version string without executing the workload code."""
    return "1.0.0"


def test_cos_agent_relation(context):
    """Test that the cos-agent endpoint writes the correct scrape jobs to rel data."""
    # GIVEN a BE charm which may not necessarily be a leader.
    cos_agent_relation = SubordinateRelation(endpoint="cos-agent")
    state = State(relations={cos_agent_relation})

    # WHEN a cos-agent relation is joined.
    with (
        context(context.on.relation_joined(cos_agent_relation), state=state) as mgr,
    ):
        state_out = mgr.run()
        cos_agent_relation = next(
            (obj for obj in state_out.relations if obj.endpoint == "cos-agent"), None
            )
        assert cos_agent_relation

        # THEN, there must be a metrics scrape jobs
        local_unit_data_config = getattr(
            cos_agent_relation, "local_unit_data", {}).get("config", {}
                                                           )
        scrape_jobs_json = json.loads(local_unit_data_config).get(
            "metrics_scrape_jobs", {}
        )
        assert scrape_jobs_json
