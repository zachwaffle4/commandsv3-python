# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A status LED, driven by a digital output. Blinks forever until canceled."""

import wpilib

import commands3 as cmd3
from commands3 import requires_self, yield_


class Light(cmd3.Mechanism):
    def __init__(self) -> None:
        super().__init__("Light")
        self._output = wpilib.DigitalOutput(1)

    @requires_self()
    async def blink(self) -> None:
        while True:
            self._output.set(True)
            await yield_()
            self._output.set(False)
            await yield_()
