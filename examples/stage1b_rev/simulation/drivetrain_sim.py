# Copyright 2026 FRCSoftware
#
# SPDX-License-Identifier: BSD-3-Clause

import rev
import telemetry
from wpilib.simulation import DifferentialDrivetrainSim, OnboardIMUSim
from wpimath import DCMotor, Pose2d, Rotation2d, units

from .fuel_sim import FuelSim

_GEAR_RATIO = 10.71
_WHEEL_RADIUS_METERS = 0.0762  # 3 inches
_LINEAR_TO_MOTOR_RATIO = (1.0 / _WHEEL_RADIUS_METERS) * _GEAR_RATIO
_BUS_VOLTAGE = 12.0


class DrivetrainSim:
    def __init__(self, left_spark: rev.SparkMax, right_spark: rev.SparkMax) -> None:
        self._left_spark = left_spark
        self._right_spark = right_spark

        self._left_spark_sim = rev.SparkMaxSim(left_spark, DCMotor.neo(2))
        self._right_spark_sim = rev.SparkMaxSim(right_spark, DCMotor.neo(2))

        self._imu_sim = OnboardIMUSim()

        self._left_encoder_sim = self._left_spark_sim.get_relative_encoder_sim()
        self._right_encoder_sim = self._right_spark_sim.get_relative_encoder_sim()

        self._drive_sim = DifferentialDrivetrainSim(
            DCMotor.neo(2),  # 2 NEO motors on each side of the drivetrain.
            _GEAR_RATIO,
            2.1,  # MOI of 2.1 kg m^2 (from CAD model).
            26.5,  # Mass of the robot is 26.5 kg.
            _WHEEL_RADIUS_METERS,  # Robot uses 3" radius (6" diameter) wheels.
            0.546,  # Distance between wheels in meters.
        )

        self._table = telemetry.get_table("Drivetrain")
        self._left_motor_table = self._table.get_table("LeftMotor")
        self._right_motor_table = self._table.get_table("RightMotor")

        self._drive_sim.set_pose(Pose2d(2.5, 2, Rotation2d()))
        FuelSim.robot_pose_supplier = self._drive_sim.get_pose

    def periodic(self) -> None:
        sim = self._drive_sim
        left_motor_voltage = self._left_spark.get_throttle() * _BUS_VOLTAGE
        right_motor_voltage = self._right_spark.get_throttle() * _BUS_VOLTAGE

        sim.set_inputs(left_motor_voltage, right_motor_voltage)
        sim.update(0.02)

        self._imu_sim.set_yaw(sim.get_heading().radians())

        self._left_encoder_sim.set_position(
            units.radians_to_rotations(
                sim.get_left_position() / _WHEEL_RADIUS_METERS * _GEAR_RATIO
            )
        )
        self._left_encoder_sim.set_velocity(
            units.radians_per_second_to_rotations_per_minute(
                sim.get_left_velocity() / _WHEEL_RADIUS_METERS * _GEAR_RATIO
            )
        )
        self._right_encoder_sim.set_position(
            units.radians_to_rotations(
                sim.get_right_position() / _WHEEL_RADIUS_METERS * _GEAR_RATIO
            )
        )
        self._right_encoder_sim.set_velocity(
            units.radians_per_second_to_rotations_per_minute(
                sim.get_right_velocity() / _WHEEL_RADIUS_METERS * _GEAR_RATIO
            )
        )

        table = self._table
        table.log("Pose", sim.get_pose())
        table.log_unit("LeftPosition", sim.get_left_position(), "m")
        table.log_unit("RightPosition", sim.get_right_position(), "m")
        table.log_unit("LeftVelocity", sim.get_left_velocity(), "m/s")
        table.log_unit("RightVelocity", sim.get_right_velocity(), "m/s")

        left, right = self._left_motor_table, self._right_motor_table
        left.log_unit(
            "MotorVelocity", sim.get_left_velocity() * _LINEAR_TO_MOTOR_RATIO, "rad/s"
        )
        right.log_unit(
            "MotorVelocity", sim.get_right_velocity() * _LINEAR_TO_MOTOR_RATIO, "rad/s"
        )
        left.log_unit("MotorVoltage", left_motor_voltage, "V")
        right.log_unit("MotorVoltage", right_motor_voltage, "V")
        left.log_unit("MotorSupplyCurrent", sim.get_left_current_draw(), "A")
        right.log_unit("MotorSupplyCurrent", sim.get_right_current_draw(), "A")

    def set_pose(self, pose: Pose2d) -> None:
        self._drive_sim.set_pose(pose)
