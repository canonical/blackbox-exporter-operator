# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
#
# The integration tests use the Jubilant library. See https://documentation.ubuntu.com/jubilant/
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
import pathlib

import jubilant
import pytest

logger = logging.getLogger(__name__)


def test_deploy(charm: pathlib.Path, juju: jubilant.Juju):
    """Deploy the charm under test."""
    juju.deploy(charm.resolve(), app="blackbox-exporter-operator")
    juju.wait(jubilant.all_active)

@pytest.mark.skip(reason="blackbox_exporter.get_version is not implemented")
def test_workload_version_is_set(charm: pathlib.Path, juju: jubilant.Juju):
    """Check that the correct version of the workload is running."""
    version = juju.status().apps["blackbox-exporter-operator"].version
    assert version == "3.14"  # Replace 3.14 by the expected version of the workload.
