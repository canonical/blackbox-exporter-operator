# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.


from unittest.mock import patch

import pytest
from scenario import Context

from charm import BlackboxExporterOperatorCharm


@pytest.fixture
def placeholder_cfg_path(tmp_path):
    return tmp_path / "blackbox.yml"

@pytest.fixture(autouse=True)
def mock_config_path(placeholder_cfg_path):
    with patch("charm.SNAP_CONFIG_PATH", placeholder_cfg_path):
        yield

@pytest.fixture(autouse=True)
def mock_hostname():
    with patch("socket.gethostname", return_value="hostname"):
        yield

@pytest.fixture(autouse=True)
def mock_is_snap_active():
    with patch("charm.is_snap_active", return_value=True) as mock:
        yield mock

@pytest.fixture
def be_charm():
    return BlackboxExporterOperatorCharm


@pytest.fixture(scope="function")
def context(be_charm):
    return Context(charm_type=be_charm)
