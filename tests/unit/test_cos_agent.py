# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
#
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/


import json
import logging
import socket

from scenario import PeerRelation, State, SubordinateRelation

PRINCIPAL_HOSTNAME = socket.gethostname()

logger = logging.getLogger(__name__)

# Simulating a peer with only ONE interface.
PEER_ONE_REL_DATA = {
    "az": "medium-vm",
    "egress-subnets": "10.223.56.245/32",
    "ingress-address": "10.223.56.245",
    "principal-hostname": "juju-4f7add-0",
    "principal-unit": "ubuntu/0",
    "private-address": "10.223.56.245",
    "unit-networks": json.dumps([
        {
            "iface": "eth0",
            "ip": "10.223.56.245",
            "net": "10.223.56.245/32",
        }
    ]),
}

# Simulating a peer which has TWO interfaces.
PEER_TWO_REL_DATA = {
    "az": "medium-vm",
    "egress-subnets": "10.223.56.245/32",
    "ingress-address": "10.223.56.245",
    "principal-hostname": "juju-4f7add-0",
    "principal-unit": "ubuntu/0",
    "private-address": "10.223.56.245",
    "unit-networks": json.dumps([
        {
            "iface": "dummy0",
            "ip": "10.10.10.1",
            "net": "10.10.10.1/32",
        },
        {
            "iface": "eth0",
            "ip": "10.223.56.245",
            "net": "10.223.56.245/32",
        },
    ]),
}


def test_self_metrics(context):
    """Test that the cos-agent endpoint writes the self monitoring scrape jobs to rel data."""
    # GIVEN a BE charm which has no peers or probes_file set via juju config.
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

        # THEN, there must be EXACTLY ONE metrics scrape jobs
        local_unit_data_config = getattr(
            cos_agent_relation, "local_unit_data", {}).get("config", {}
                                                           )
        scrape_jobs_json = json.loads(local_unit_data_config).get(
            "metrics_scrape_jobs", {}
        )
        assert scrape_jobs_json

        assert len(scrape_jobs_json) == 1

        # AND the name of that single job must be `be-self-monitoring`
        assert scrape_jobs_json[0].get("job_name", "") == "be-self-monitoring"

def test_connectivity_checks_metrics_one_peer(context):
    """Test that the cos-agent endpoint writes the correct jobs to rel data."""
    # GIVEN a BE charm which has EXACTLY ONE peer and no probes_file set via juju config.
    cos_agent_relation = SubordinateRelation(endpoint="cos-agent")
    peer_relation = PeerRelation(endpoint="peers", peers_data={1: PEER_ONE_REL_DATA})
    state = State(relations={cos_agent_relation, peer_relation})

    # WHEN a reconcile happens.
    with (
        context(context.on.update_status(), state=state) as mgr,
    ):
        state_out = mgr.run()
        cos_agent_relation = next(
            (obj for obj in state_out.relations if obj.endpoint == "cos-agent"), None
            )
        assert cos_agent_relation

        # THEN, there must be EXACTLY TWO metrics scrape jobs
        # 1. for self monitoring and 2. for auto cross-unit-connectivity checks to the sole peer.
        # Note: charm.py adds the scrape jobs in the order below.
        # 1. The self monitoring job
        # 2. Automatic connectivity checks
        # 3. probes_file jobs
        # So the assumptions below that the first job will be for self monitoring etc is safe.
        local_unit_data_config = getattr(
            cos_agent_relation, "local_unit_data", {}).get("config", {}
                                                           )
        scrape_jobs_json = json.loads(local_unit_data_config).get(
            "metrics_scrape_jobs", {}
        )
        assert scrape_jobs_json

        assert len(scrape_jobs_json) == 2

        # AND the name of that first job must be `be-self-monitoring`
        assert scrape_jobs_json[0].get("job_name", "") == "be-self-monitoring"

        # AND the name of the second job must be equal to the principal host name
        assert scrape_jobs_json[1].get(
            "job_name", ""
            ) == f"{PRINCIPAL_HOSTNAME}-connectivity-checks"

        # AND since there is only 1 peer with only 1 interface,
        # the length of `static_configs` must be EXACTLY 1.
        static_configs = scrape_jobs_json[1].get("static_configs", {})
        assert len(static_configs) == 1

def test_connectivity_checks_metrics_two_peers(context):
    """Test that the cos-agent endpoint writes the correct jobs to rel data."""
    # GIVEN a BE charm which has TWO peers and no probes_file set via juju config.
    cos_agent_relation = SubordinateRelation(endpoint="cos-agent")
    peer_relation = PeerRelation(
        endpoint="peers", peers_data={1: PEER_ONE_REL_DATA, 2: PEER_TWO_REL_DATA}
        )
    state = State(relations={cos_agent_relation, peer_relation})

    # WHEN a reconcile happens.
    with (
        context(context.on.update_status(), state=state) as mgr,
    ):
        state_out = mgr.run()
        cos_agent_relation = next(
            (obj for obj in state_out.relations if obj.endpoint == "cos-agent"), None
            )
        assert cos_agent_relation

        # THEN, there must be EXACTLY TWO metrics scrape jobs
        # 1. for self monitoring and 2. for auto cross-unit-connectivity checks to the sole peer.
        local_unit_data_config = getattr(
            cos_agent_relation, "local_unit_data", {}).get("config", {}
                                                           )
        scrape_jobs_json = json.loads(local_unit_data_config).get(
            "metrics_scrape_jobs", {}
        )
        assert scrape_jobs_json

        assert len(scrape_jobs_json) == 2

        # AND the name of that first job must be `be-self-monitoring`
        assert scrape_jobs_json[0].get("job_name", "") == "be-self-monitoring"

        # AND the name of the second job must be equal to the principal host name
        assert scrape_jobs_json[1].get(
            "job_name", ""
            ) == f"{PRINCIPAL_HOSTNAME}-connectivity-checks"

        # AND since there are 2 peers, one with 1 interface and one with 2 interfaces,
        # the length of static_configs for this job must be EXACTLY three.
        static_configs = scrape_jobs_json[1].get("static_configs", {})
        assert len(static_configs) == 3
