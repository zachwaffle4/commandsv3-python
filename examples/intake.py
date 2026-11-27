# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A simple roller intake: run inward to grab, outward to release."""

import wpilib

import commands3 as cmd3
from commands3 import command, wait


class Intake(cmd3.Mechanism):
    def __init__(self) -> None:
        super().__init__("Intake")
        self._motor = wpilib.PWMMotorController(3)

    @command
    async def set_throttle(self, throttle: float) -> None:
        self._motor.set_throttle(throttle)

    @command
    async def grab(self) -> None:
        await self.set_throttle(1.0)
        await wait(0.5)
        await self.set_throttle(0.0)

    @command
    async def release(self) -> None:
        await self.set_throttle(-1.0)
        await wait(0.5)
        await self.set_throttle(0.0)
