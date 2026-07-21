# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A two-motor differential drivetrain, driven from OI callables every tick."""

from collections.abc import Callable

import wpilib

import commands3 as cmd3
from commands3 import requires_self, yield_


class Drivetrain(cmd3.Mechanism):
    def __init__(self) -> None:
        super().__init__("Drivetrain")
        self._left = wpilib.PWMSparkMax(0)
        self._right = wpilib.PWMSparkMax(1)
        self._right.set_inverted(True)

    @requires_self("Arcade Drive")
    async def arcade_drive(
        self, forward: Callable[[], float], rotate: Callable[[], float]
    ) -> None:
        """Runs forever, applying `forward()`/`rotate()` to the motors every tick."""
        while True:
            f, r = forward(), rotate()
            self._left.set_throttle(f + r)
            self._right.set_throttle(f - r)
            await yield_()

    @requires_self("Stop")
    async def stop(self) -> None:
        self._left.set_throttle(0.0)
        self._right.set_throttle(0.0)
