# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.


import pytest
from scenario import Context

from charm import BlackboxExporterOperatorCharm


@pytest.fixture
def be_charm():
    return BlackboxExporterOperatorCharm


@pytest.fixture(scope="function")
def context(be_charm):
    return Context(charm_type=be_charm)
