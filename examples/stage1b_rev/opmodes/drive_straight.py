# Copyright 2026 FRCSoftware
#
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from typing import TYPE_CHECKING

import commands3 as cmd3
from wpilib.opmodes import OpMode, autonomous

if TYPE_CHECKING:
    from robot import Robot


@autonomous
class DriveStraight(OpMode):
    def __init__(self, robot: Robot) -> None:
        super().__init__()
        self.robot = robot

    def start(self) -> None:
        cmd3.Scheduler.get_default().schedule(
            self.robot.drivetrain.arcade_drive(lambda: 0.5, lambda: 0.0).with_timeout(4)
        )
