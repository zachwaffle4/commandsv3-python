# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Checks that each ``commands3.robot_mode_triggers`` factory reads the robot
state it claims to, by running a real robot through real driver station
transitions. The factories are one-liners over ``RobotState``, but they are
exactly the kind of one-liner that is easy to wire to the wrong predicate.
"""

from wpilib.testing.controller import RobotTestController


def test_autonomous_trigger_runs_only_in_enabled_autonomous(control, robot):
    with control.run_robot():
        control.step_timing(seconds=1, autonomous=True, enabled=True)
        assert robot.auto_marker.ticks > 0

        ticks_after_auto = robot.auto_marker.ticks
        control.step_timing(seconds=1, autonomous=False, enabled=True)

        assert robot.auto_marker.ticks == ticks_after_auto
        assert robot.teleop_marker.ticks > 0


def test_teleop_trigger_stops_when_the_robot_is_disabled(control, robot):
    with control.run_robot():
        control.step_timing(seconds=1, autonomous=False, enabled=True)
        assert robot.teleop_marker.ticks > 0

        ticks_while_enabled = robot.teleop_marker.ticks
        control.step_timing(seconds=1, autonomous=False, enabled=False)

        assert robot.teleop_marker.ticks == ticks_while_enabled


def test_disabled_trigger_runs_only_while_disabled(control, robot):
    with control.run_robot():
        control.step_timing(seconds=1, autonomous=False, enabled=False)
        assert robot.disabled_marker.ticks > 0

        ticks_while_disabled = robot.disabled_marker.ticks
        control.step_timing(seconds=1, autonomous=False, enabled=True)

        assert robot.disabled_marker.ticks == ticks_while_disabled


def test_utility_trigger_does_not_fire_in_auto_or_teleop(
    control: RobotTestController, robot
):
    with control.run_robot():
        control.step_timing(seconds=1, autonomous=True, enabled=True)
        control.step_timing(seconds=1, autonomous=False, enabled=True)

        assert robot.utility_marker.ticks == 0
