# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
A single-motor arm with an absolute encoder measuring how far it is below the
top. Uses `@command` so each method reads like a plain instance method but
returns a `Command` that claims this mechanism.
"""

import wpilib

import commands3 as cmd3
from commands3 import GeneratorCommand, command, wait_until

_TOP_READING = 0.0
_TOP_TOLERANCE = 1.0


class Arm(cmd3.Mechanism):
    def __init__(self) -> None:
        super().__init__("Arm")
        self._motor = wpilib.PWMMotorController(2)
        self._encoder = wpilib.DutyCycleEncoder(4, 360.0, _TOP_READING)

    def at_top(self) -> bool:
        return self._encoder.get() <= _TOP_TOLERANCE

    @command
    async def raise_arm(self) -> None:
        self._motor.set_throttle(0.5)
        await wait_until(self.at_top)
        self._motor.set_throttle(0.0)

    @command
    async def lower_arm(self, degrees: float = 45.0) -> GeneratorCommand:
        """Lowers the arm until it is `degrees` below the top."""
        self._motor.set_throttle(-0.3)
        while self._encoder.get() < degrees:
            yield
        self._motor.set_throttle(0.0)

    @command
    async def hold(self) -> None:
        self._motor.set_throttle(0.0)
        await cmd3.park()
