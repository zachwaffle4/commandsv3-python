# Copyright 2026 FRCSoftware
#
# SPDX-License-Identifier: BSD-3-Clause

"""Run with `python -m robotpy test` from this project's directory."""

import hal
from wpilib.simulation import XboxControllerSim
from wpilib.testing import OpMode

DRIVE_STRAIGHT = OpMode(hal.RobotMode.AUTONOMOUS, "DriveStraight")
DRIVE_BACK_THEN_SHOOT = OpMode(hal.RobotMode.AUTONOMOUS, "DriveBackThenShoot")
MY_TELEOP = OpMode(hal.RobotMode.TELEOPERATED, "MyTeleop")

START_X = 2.5  # DrivetrainSim's initial pose


def _x(robot) -> float:
    return robot.drivetrain._drivetrain_sim._drive_sim.get_pose().x


def test_drive_straight_drives_forward_then_stops(control, robot):
    with control.run_robot():
        control.step_timing(seconds=3, opmode=DRIVE_STRAIGHT, enabled=True)
        assert _x(robot) > START_X + 1.0

        control.step_timing(seconds=2, opmode=DRIVE_STRAIGHT, enabled=True)
        stopped_x = _x(robot)
        control.step_timing(seconds=1, opmode=DRIVE_STRAIGHT, enabled=True)
        assert abs(_x(robot) - stopped_x) < 0.05


def test_drive_back_then_shoot(control, robot):
    with control.run_robot():
        control.step_timing(seconds=2.5, opmode=DRIVE_BACK_THEN_SHOOT, enabled=True)
        assert _x(robot) < START_X
        assert robot.feeder._motor.get_throttle() == 0.75
        # The launcher spins up for 2 s before driving its motor.
        assert robot.intake_launcher._motor.get_throttle() == 0.0

        control.step_timing(seconds=2.5, opmode=DRIVE_BACK_THEN_SHOOT, enabled=True)
        assert robot.intake_launcher._motor.get_throttle() == 0.9


def test_teleop_bumper_intakes(control, robot):
    with control.run_robot():
        xbox = XboxControllerSim(0)
        control.step_timing(seconds=0.5, opmode=MY_TELEOP, enabled=True)
        assert robot.feeder._motor.get_throttle() == 0.0

        xbox.set_left_bumper_button(True)
        xbox.notify_new_data()
        control.step_timing(seconds=0.5, opmode=MY_TELEOP, enabled=True)
        assert robot.intake_launcher._motor.get_throttle() == 0.8
        assert robot.feeder._motor.get_throttle() == -1.0

        xbox.set_left_bumper_button(False)
        xbox.notify_new_data()
        control.step_timing(seconds=0.5, opmode=MY_TELEOP, enabled=True)
        assert robot.feeder._motor.get_throttle() == 0.0
