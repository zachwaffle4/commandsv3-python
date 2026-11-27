# Copyright 2026 FRCSoftware
#
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import rev
import telemetry
from wpilib.simulation import FlywheelSim
from wpimath import DCMotor, Models

from .fuel_sim import FuelSim

_BUS_VOLTAGE = 12.0


class SingleFlywheelSim:
    @staticmethod
    def for_intake_launcher(motor: rev.SparkMax) -> SingleFlywheelSim:
        """Creates the physics sim for the intake launcher."""
        sim = SingleFlywheelSim(motor, "IntakeLauncher")
        FuelSim.intake_launcher_volts_supplier = sim._flywheel_sim.get_input_voltage
        return sim

    @staticmethod
    def for_feeder(motor: rev.SparkMax) -> SingleFlywheelSim:
        """Creates the physics sim for the feeder."""
        sim = SingleFlywheelSim(motor, "Feeder")
        FuelSim.feeder_volts_supplier = sim._flywheel_sim.get_input_voltage
        return sim

    def __init__(self, motor: rev.SparkMax, name: str) -> None:
        self._motor = motor
        gearbox = DCMotor.neo(1)
        self._flywheel_sim = FlywheelSim(
            Models.flywheel_from_physical_constants(gearbox, 0.001, 1.0), gearbox
        )
        self._table = telemetry.get_table(name)
        self._rotor_position_rad = 0.0

    def periodic(self) -> None:
        motor_voltage = self._motor.get_throttle() * _BUS_VOLTAGE

        self._flywheel_sim.set_input_voltage(motor_voltage)
        self._flywheel_sim.update(0.02)

        rad_per_sec = self._flywheel_sim.get_angular_velocity()
        self._rotor_position_rad += rad_per_sec * 0.02

        self._table.log_unit("MotorVoltage", motor_voltage, "V")
        self._table.log_unit("MotorVelocity", rad_per_sec, "rad/s")
        self._table.log_unit("Current", self._flywheel_sim.get_current_draw(), "A")
        self._table.log_unit("MotorPosition", self._rotor_position_rad, "rad")
