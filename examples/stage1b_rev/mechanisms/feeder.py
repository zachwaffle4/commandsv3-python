# Copyright 2026 FRCSoftware
#
# SPDX-License-Identifier: BSD-3-Clause

import commands3 as cmd3
import rev
import wpilib
from commands3 import GeneratorCommand, command

from simulation.single_flywheel_sim import SingleFlywheelSim


# [CheckupFeeder]
class Feeder(cmd3.Mechanism):
    def __init__(self) -> None:
        super().__init__("Feeder")
        self._motor = rev.SparkMax(
            wpilib.CANPort.CAN_S0, 5, rev.SparkLowLevel.MotorType.BRUSHLESS
        )
        self._sim = SingleFlywheelSim.for_feeder(self._motor)

        self.set_default_command(self.idle())

    @command(name="Feed")
    async def feed(self) -> GeneratorCommand:
        while True:
            self._motor.set_throttle(0.75)
            yield

    @command(name="Intake")
    async def intake(self) -> GeneratorCommand:
        while True:
            self._motor.set_throttle(-1.0)
            yield

    @command(name="Outtake")
    async def outtake(self) -> GeneratorCommand:
        while True:
            self._motor.set_throttle(1.0)
            yield

    @command(name="Idle")
    async def idle(self) -> GeneratorCommand:
        while True:
            self._motor.set_throttle(0.0)
            yield

    def periodic(self) -> None:
        if wpilib.RobotBase.is_simulation():
            self._sim.periodic()


# [/CheckupFeeder]
