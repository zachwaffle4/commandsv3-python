# Copyright 2026 FRCSoftware
#
# SPDX-License-Identifier: BSD-3-Clause

import commands3 as cmd3
import rev
import wpilib
from commands3 import GeneratorCommand, command, wait

from simulation.single_flywheel_sim import SingleFlywheelSim


# [CheckupIntake]
class IntakeLauncher(cmd3.Mechanism):
    def __init__(self) -> None:
        super().__init__("IntakeLauncher")
        self._motor = rev.SparkMax(
            wpilib.CANPort.CAN_S0, 4, rev.SparkLowLevel.MotorType.BRUSHLESS
        )
        self._sim = SingleFlywheelSim.for_intake_launcher(self._motor)

        self.set_default_command(self.idle())

    @command(name="Shoot")
    async def shoot(self) -> GeneratorCommand:
        await wait(2)
        while True:
            self._motor.set_throttle(0.9)
            yield

    @command(name="Intake")
    async def intake(self) -> GeneratorCommand:
        while True:
            self._motor.set_throttle(0.8)
            yield

    @command(name="Outtake")
    async def outtake(self) -> GeneratorCommand:
        while True:
            self._motor.set_throttle(-0.8)
            yield

    @command(name="Idle")
    async def idle(self) -> GeneratorCommand:
        while True:
            self._motor.set_throttle(0.0)
            yield

    def periodic(self) -> None:
        if wpilib.RobotBase.is_simulation():
            self._sim.periodic()


# [/CheckupIntake]
