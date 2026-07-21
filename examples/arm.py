# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
A single-motor arm, gated by a limit switch at the top. Uses `requires_self`
so each method reads like a plain instance method but returns a `Command`
that claims this mechanism.
"""

import wpilib

import commands3 as cmd3
from commands3 import requires_self, wait_until, yield_


class Arm(cmd3.Mechanism):
    def __init__(self) -> None:
        super().__init__("Arm")
        self._motor = wpilib.PWMSparkMax(2)
        self._top_limit = wpilib.DigitalInput(0)

    def at_top(self) -> bool:
        return not self._top_limit.get()  # limit switches read low when pressed

    @requires_self()
    async def raise_arm(self) -> None:
        self._motor.set_throttle(0.5)
        await wait_until(self.at_top)
        self._motor.set_throttle(0.0)

    @requires_self()
    async def lower_arm(self, seconds: float = 1.0) -> None:
        timer = wpilib.Timer()
        timer.start()
        self._motor.set_throttle(-0.3)
        while not timer.has_elapsed(seconds):
            await yield_()
        self._motor.set_throttle(0.0)

    @requires_self()
    async def hold(self) -> None:
        self._motor.set_throttle(0.0)
        await cmd3.park()
