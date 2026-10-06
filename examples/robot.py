# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
A small teleoperated robot wiring the example subsystems together, matching
how a real robot project is structured: mechanisms are created in the
robot's `__init__`, given default commands, and bound to controller input
through `Trigger`s inside an opmode.

Commands v3 has no robot base class of its own - you extend
`wpilib.OpModeRobot` directly and call `Scheduler.run()` yourself from
`robot_periodic()`. Bindings created while an opmode is active are
automatically scoped to it, so the ones made in `TeleopOpMode.start()`
below are torn down when that opmode ends - no manual cleanup needed. For
programs not using opmodes at all, `commands3.robot_mode_triggers.teleop()`
and friends give you the same scoping off the robot mode instead.

Launch with the RobotPy CLI, e.g. `python -m robotpy sim` from this
directory - this file isn't meant to be run directly with plain `python`.
"""

import wpilib
from wpilib.opmodes import OpMode, teleop

import commands3 as cmd3

from .arm import Arm
from .drivetrain import Drivetrain
from .intake import Intake


class Robot(wpilib.OpModeRobot):
    def __init__(self) -> None:
        super().__init__()

        self.drivetrain = Drivetrain()
        self.arm = Arm()
        self.intake = Intake()
        self.controller = wpilib.XboxController(0)

        cmd3.Scheduler.get_default().set_default_command(
            self.drivetrain,
            self.drivetrain.arcade_drive(
                lambda: -self.controller.get_left_y(),
                lambda: self.controller.get_right_x(),
            ),
        )

    def robot_periodic(self) -> None:
        cmd3.Scheduler.get_default().run()


@teleop
class TeleopOpMode(OpMode):
    def __init__(self, robot: Robot) -> None:
        super().__init__()
        self.robot = robot

    def start(self) -> None:
        controller = self.robot.controller

        raise_button = cmd3.Trigger(controller.get_left_bumper_button)
        raise_button.while_true(self.robot.arm.raise_arm())

        grab_button = cmd3.Trigger(controller.get_a_button)
        grab_button.on_true(self.robot.intake.grab())

        release_button = cmd3.Trigger(controller.get_right_bumper_button)
        release_button.on_true(self.robot.intake.release())


if __name__ == "__main__":
    Robot.main(Robot)
