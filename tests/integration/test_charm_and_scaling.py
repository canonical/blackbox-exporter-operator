# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
#
# The integration tests use the Jubilant library. See https://documentation.ubuntu.com/jubilant/
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
import pathlib

import jubilant

logger = logging.getLogger(__name__)

APP_NAME = "blackbox-exporter-operator"


def test_deploy(charm: pathlib.Path, juju: jubilant.Juju):
    """Deploy the charm under test."""
    juju.deploy(charm.resolve(), app=APP_NAME)
    juju.deploy("ubuntu")
    juju.integrate(APP_NAME, "ubuntu")
    juju.wait(jubilant.all_active)


def test_scale_up_on_same_machine(juju: jubilant.Juju):
    """Test scaling the principal of the charm by deploying another principal unit.

    The other principal will be deployed on the same machine.
    """
    juju.add_unit("ubuntu", to="0")
    juju.wait(jubilant.all_active)


def test_scale_up_on_different_machine(juju: jubilant.Juju):
    """Test scaling the principal of the charm by deploying another principal unit.

    The other principal will be deployed on a different machine.
    """
    juju.add_unit("ubuntu")
    juju.wait(jubilant.all_active)


def test_scale_down_on_the_machine(juju: jubilant.Juju):
    """On the machine with 2 units of BE.

    We test scaling down and ensure the snap is not removed until the last unit is removed.
    """
    # On machine 0, we have two Ubuntu principals and hence, two BEs.
    # If we remove 1 of the 2 principals, the BE subordinate related to it will also be removed.
    juju.remove_unit("ubuntu/1")
    juju.wait(jubilant.all_active)

    # Now that one of the 2 units of BE on machine 0 is removed,
    # we need to make sure that the snap was not uninstalled
    # by the unit that was removed.
    # This is because we still have one unit on the machine which needs the snap.
    snap_list = juju.ssh(f"{APP_NAME}/leader", "sudo snap list")
    assert "prometheus-blackbox-exporter" in snap_list

    # We'll remove the remaining unit and ensure that the snap is also removed from the machine.
    juju.remove_application(APP_NAME)
    juju.wait(jubilant.all_active)
    snap_list = juju.ssh(f"{APP_NAME}/leader", "sudo snap list")
    assert "prometheus-blackbox-exporter" not in snap_list
