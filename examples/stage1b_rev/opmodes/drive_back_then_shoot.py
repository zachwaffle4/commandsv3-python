# Copyright 2026 FRCSoftware
#
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from typing import TYPE_CHECKING

import commands3 as cmd3
from commands3 import all_of, await_, command
from wpilib.opmodes import OpMode, autonomous

if TYPE_CHECKING:
    from robot import Robot


@autonomous
class DriveBackThenShoot(OpMode):
    def __init__(self, robot: Robot) -> None:
        super().__init__()
        self.robot = robot

    def _auto_command(self) -> cmd3.Command:
        robot = self.robot

        @command(name="Drive Back Then Shoot")
        async def body() -> None:
            await robot.drivetrain.arcade_drive(lambda: -0.2, lambda: 0.0).with_timeout(2)
            await all_of([robot.intake_launcher.shoot(), robot.feeder.feed()])

        return body()

    def start(self) -> None:
        cmd3.Scheduler.get_default().schedule(self._auto_command())
