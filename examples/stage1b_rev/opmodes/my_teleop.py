# Copyright 2026 FRCSoftware
#
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from typing import TYPE_CHECKING

import commands3 as cmd3
from wpilib.opmodes import OpMode, teleop

if TYPE_CHECKING:
    from robot import Robot


@teleop
class MyTeleop(OpMode):
    def __init__(self, robot: Robot) -> None:
        super().__init__()
        self.robot = robot
        xbox = cmd3.CommandXboxController(0)
        self.xbox = xbox

        robot.drivetrain.set_default_command(
            robot.drivetrain.arcade_drive(
                lambda: -xbox.get_left_y(), lambda: xbox.get_right_x()
            )
        )

        xbox.left_bumper().while_true(robot.intake_launcher.intake()).while_true(
            robot.feeder.intake()
        )

        xbox.right_bumper().while_true(robot.intake_launcher.shoot()).while_true(
            robot.feeder.feed()
        )

        xbox.a().while_true(robot.intake_launcher.outtake()).while_true(
            robot.feeder.outtake()
        )

    def periodic(self) -> None:
        pass
