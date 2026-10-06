# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Binding scopes and default commands, end to end. `tests/` covers the same
logic against a fake `RobotStateFetcher`; what these add is proof that
`DriverStationRobotStateFetcher` reads the values the scopes expect, so a
binding really does go away when the driver station changes opmode.
"""

import hal
from robot import AUTO_OPMODE_NAME, TELEOP_OPMODE_NAME
from wpilib.testing import OpMode

AUTO_OPMODE = OpMode(hal.RobotMode.AUTONOMOUS, AUTO_OPMODE_NAME)
TELEOP_OPMODE = OpMode(hal.RobotMode.TELEOPERATED, TELEOP_OPMODE_NAME)


def test_default_command_runs_in_every_enabled_mode(control, robot):
    with control.run_robot():
        control.step_timing(seconds=1, autonomous=True, enabled=True)
        after_auto = robot.elevator.ticks
        assert after_auto > 0

        control.step_timing(seconds=1, autonomous=False, enabled=True)
        assert robot.elevator.ticks > after_auto


def test_uncontrollable_default_command_stops_while_disabled(control, robot):
    # The real-driver-station counterpart to tests/test_scheduler_disabled.py:
    # proves DriverStationRobotStateFetcher.is_enabled() is what the
    # scheduler's disabled-mode handling actually reads.
    with control.run_robot():
        control.step_timing(seconds=1, autonomous=False, enabled=True)
        ticks_while_enabled = robot.elevator.ticks
        assert ticks_while_enabled > 0

        control.step_timing(seconds=1, autonomous=False, enabled=False)
        assert robot.elevator.ticks == ticks_while_enabled

        control.step_timing(seconds=1, autonomous=False, enabled=True)
        assert robot.elevator.ticks > ticks_while_enabled


def test_binding_made_inside_an_opmode_runs_while_it_is_selected(control, robot):
    with control.run_robot():
        robot.button_pressed = True
        control.step_timing(seconds=1, opmode=TELEOP_OPMODE, enabled=True)

        assert robot.opmode_marker.ticks > 0


def test_binding_made_inside_an_opmode_is_torn_down_when_it_ends(control, robot):
    with control.run_robot():
        robot.button_pressed = True
        control.step_timing(seconds=1, opmode=TELEOP_OPMODE, enabled=True)
        ticks_in_teleop = robot.opmode_marker.ticks
        assert ticks_in_teleop > 0

        # Same signal, different opmode: the binding's scope is gone, so
        # the command must not be rescheduled.
        control.step_timing(seconds=1, opmode=AUTO_OPMODE, enabled=True)

        assert robot.opmode_marker.ticks == ticks_in_teleop


def test_globally_scoped_bindings_survive_an_opmode_change(control, robot):
    # The mode triggers are bound in the robot constructor, before the
    # program is marked started, so they land in the global scope and must
    # keep working across opmode transitions.
    with control.run_robot():
        control.step_timing(seconds=1, opmode=TELEOP_OPMODE, enabled=True)
        assert robot.teleop_marker.ticks > 0

        control.step_timing(seconds=1, opmode=AUTO_OPMODE, enabled=True)
        auto_ticks = robot.auto_marker.ticks
        assert auto_ticks > 0

        control.step_timing(seconds=1, opmode=TELEOP_OPMODE, enabled=True)
        assert robot.auto_marker.ticks == auto_ticks
