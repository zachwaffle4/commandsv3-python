# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A simple roller intake: run inward to grab, outward to release."""

import wpilib

import commands3 as cmd3
from commands3 import wait, requires_self


class Intake(cmd3.Mechanism):
    def __init__(self) -> None:
        super().__init__("Intake")
        self._motor = wpilib.PWMSparkMax(3)

    @requires_self()
    async def set_throttle(self, throttle: float) -> None:
        self._motor.set_throttle(throttle)

    @requires_self("Grab")
    async def grab(self) -> None:
        await self.set_throttle(1.0)
        await wait(0.5)
        await self.set_throttle(0.0)

    @requires_self("Release")
    async def release(self) -> None:
        await self.set_throttle(-1.0)
        await wait(0.5)
        await self.set_throttle(0.0)
