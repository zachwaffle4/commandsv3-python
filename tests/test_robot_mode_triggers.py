# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Smoke tests for the ``button.robot_mode_triggers`` factories. Java has no
test suite for ``RobotModeTriggers`` either - the factories are one-liners
over ``RobotState``, and asserting on their values would mean pulling in
driver station simulation, which this suite deliberately avoids.
"""

import pytest

from commands3 import Trigger
from commands3.button import autonomous, disabled, teleop, utility


@pytest.mark.parametrize("factory", [autonomous, teleop, disabled, utility])
def test_factory_returns_a_trigger(factory):
    trigger = factory()

    assert isinstance(trigger, Trigger)
    # The condition is readable without the robot being in any particular
    # state; we only care that it doesn't raise.
    assert isinstance(trigger.get_as_boolean(), bool)
