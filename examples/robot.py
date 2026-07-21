# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
A small teleoperated robot wiring the example subsystems together with
`CommandRobot`, matching how a real robot project is structured: mechanisms
are created in the robot's `__init__`, given default commands, and bound to
controller input through `Trigger`s inside a teleop opmode.

Launch with the RobotPy CLI, e.g. `python -m robotpy sim` from this
directory - this file isn't meant to be run directly with plain `python`.
"""

import wpilib

import commands3 as cmd3

from .arm import Arm
from .drivetrain import Drivetrain
from .intake import Intake


class Robot(cmd3.CommandRobot):
    def __init__(self) -> None:
        super().__init__()

        self.drivetrain = Drivetrain()
        self.arm = Arm()
        self.intake = Intake()
        self.controller = wpilib.XboxController(0)

        teleop = self.create_teleop_opmode("Teleoperated")

        teleop.set_default_command(
            self.drivetrain,
            self.drivetrain.arcade_drive(
                lambda: -self.controller.get_left_y(),
                lambda: self.controller.get_right_x(),
            ),
        )

        raise_button = teleop.enabled(cmd3.Trigger(self.controller.get_left_bumper_button))
        raise_button.while_true(self.arm.raise_arm())

        grab_button = teleop.enabled(cmd3.Trigger(self.controller.get_a_button))
        grab_button.on_true(self.intake.grab())

        release_button = teleop.enabled(cmd3.Trigger(self.controller.get_right_bumper_button))
        release_button.on_true(self.intake.release())

        self.publish_opmodes()

    def robot_periodic(self) -> None:
        cmd3.Scheduler.get_default().run()


if __name__ == "__main__":
    Robot.main(Robot)
