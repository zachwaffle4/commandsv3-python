# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A status LED, driven by a digital output. Blinks forever until canceled."""

import wpilib

import commands3 as cmd3
from commands3 import GeneratorCommand, command


class Light(cmd3.Mechanism):
    def __init__(self) -> None:
        super().__init__("Light")
        self._output = wpilib.DigitalOutput(5)

    def controllable_during_disabled(self) -> bool:
        # An LED can't hurt anyone, so let it keep blinking while the robot
        # is disabled. Mechanisms that move stay off-limits by default.
        return True

    @command
    async def blink(self) -> GeneratorCommand:
        while True:
            self._output.set(True)
            yield
            self._output.set(False)
            yield
