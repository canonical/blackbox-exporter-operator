# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import patch

import pytest
from ops import pebble
from scenario import Container, Context, Exec

from charm import BlackboxExporterOperatorCharm


@pytest.fixture
def be_charm():
    return BlackboxExporterOperatorCharm


@pytest.fixture(scope="function")
def context(be_charm):
    return Context(charm_type=be_charm)
