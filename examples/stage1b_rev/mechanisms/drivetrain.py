# Copyright 2026 FRCSoftware
#
# SPDX-License-Identifier: BSD-3-Clause

from collections.abc import Callable

import commands3 as cmd3
import rev
import wpilib
from commands3 import GeneratorCommand, command

from simulation.drivetrain_sim import DrivetrainSim

_BRUSHLESS = rev.SparkLowLevel.MotorType.BRUSHLESS
_RESET = rev.ResetMode.RESET_SAFE_PARAMETERS
_PERSIST = rev.PersistMode.PERSIST_PARAMETERS


# [CheckUpDrivetrain]
class Drivetrain(cmd3.Mechanism):
    def __init__(self) -> None:
        super().__init__("Drivetrain")
        can = wpilib.CANPort.CAN_S0
        self._left_leader = rev.SparkMax(can, 0, _BRUSHLESS)
        self._left_follower = rev.SparkMax(can, 1, _BRUSHLESS)
        self._right_leader = rev.SparkMax(can, 2, _BRUSHLESS)
        self._right_follower = rev.SparkMax(can, 3, _BRUSHLESS)

        self._imu = wpilib.OnboardIMU(wpilib.OnboardIMU.MountOrientation.FLAT)
        self._differential_drive = wpilib.DifferentialDrive(
            self._left_leader.set_throttle, self._right_leader.set_throttle
        )

        self._drivetrain_sim = DrivetrainSim(self._left_leader, self._right_leader)

        left_config = rev.SparkMaxConfig().inverted(True)
        self._left_leader.configure(left_config, _RESET, _PERSIST)
        self._left_follower.configure(
            left_config.follow(self._left_leader), _RESET, _PERSIST
        )

        right_config = rev.SparkMaxConfig().inverted(False)
        self._right_leader.configure(right_config, _RESET, _PERSIST)
        self._right_follower.configure(
            right_config.follow(self._right_leader), _RESET, _PERSIST
        )

        self.set_default_command(self.idle())

    @command(name="Idle")
    async def idle(self) -> GeneratorCommand:
        while True:
            self._differential_drive.arcade_drive(0.0, 0.0)
            yield

    @command(name="Drive")
    async def arcade_drive(
        self,
        forward_throttle: Callable[[], float],
        rotation_throttle: Callable[[], float],
    ) -> GeneratorCommand:
        while True:
            self._differential_drive.arcade_drive(
                forward_throttle(), rotation_throttle()
            )
            yield

    def periodic(self) -> None:
        if wpilib.RobotBase.is_simulation():
            self._drivetrain_sim.periodic()


# [/CheckUpDrivetrain]
