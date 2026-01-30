# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
#
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
from unittest.mock import patch

import pytest
from ops import testing
from scenario import State

logger = logging.getLogger(__name__)

mock_ports = [80, 443]

VALID_CONFIG = """
modules:
  icmp:
    prober: icmp
    timeout: 10s
    icmp:
      preferred_ip_protocol: "ip4"
      ip_protocol_fallback: true
"""

INVALID_YAML_CONFIG = """
modules:
something
    somethingelse:
"""

VALID_YAML_WITH_NO_MODULES_SECTION = """
tcp_connect:
    prober: tcp
    timeout: 10s
  icmp:
    prober: icmp
    timeout: 10s
"""

VALID_YAML_WITH_BAD_MODULES = """
modules:
  non-existing-module:
    prober: tcp
    timeout: 10s
"""

@pytest.mark.parametrize(
    "config, expected_status, should_restart",
    [
        (VALID_CONFIG, testing.ActiveStatus, True),
        (INVALID_YAML_CONFIG, testing.BlockedStatus, False),
        (VALID_YAML_WITH_NO_MODULES_SECTION, testing.BlockedStatus, False),
        (VALID_YAML_WITH_BAD_MODULES, testing.ActiveStatus, True),
    ],
)
def test_config_validation(context, config, expected_status, should_restart):
    state = State(config={"config_file": config})
    with patch("charm.BlackboxExporterOperatorCharm._restart_snap") as mock_restart:
        state_out = context.run(context.on.config_changed(), state=state)
        assert isinstance(state_out.unit_status, expected_status)
        if should_restart:
            mock_restart.assert_called()
        else:
            mock_restart.assert_not_called()
