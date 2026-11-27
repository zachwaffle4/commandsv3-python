# Copyright 2026 FRCSoftware
#
# SPDX-License-Identifier: BSD-3-Clause

"""
The methods in this class are called automatically as described in the
OpModeRobot documentation. OpMode classes in the `opmodes` package next to
this file are automatically registered to display in the Driver Station.

Launch with the RobotPy CLI from this directory, e.g. `python -m robotpy sim`.
"""

import commands3 as cmd3
import wpilib

from mechanisms.drivetrain import Drivetrain
from mechanisms.feeder import Feeder
from mechanisms.intake_launcher import IntakeLauncher
from simulation.fuel_sim import FuelSim


class Robot(wpilib.OpModeRobot):
    def __init__(self) -> None:
        super().__init__()
        self.drivetrain = Drivetrain()
        self.intake_launcher = IntakeLauncher()
        self.feeder = Feeder()

    def robot_periodic(self) -> None:
        cmd3.Scheduler.get_default().run()
        self.drivetrain.periodic()
        self.intake_launcher.periodic()
        self.feeder.periodic()
        if wpilib.RobotBase.is_simulation():
            FuelSim.periodic()


if __name__ == "__main__":
    Robot.main(Robot)
