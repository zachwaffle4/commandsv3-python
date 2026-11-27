# Copyright 2026 FRCSoftware
#
# SPDX-License-Identifier: BSD-3-Clause

import enum
from collections.abc import Callable
from typing import ClassVar

import telemetry
from wpimath import Pose2d, Pose3d, Rotation3d, Transform3d


class _Mode(enum.Enum):
    INTAKE = enum.auto()
    SHOOT = enum.auto()
    OUTTAKE = enum.auto()


_SHOT_DT = 0.1
_SHOT_VELOCITY_X = -2.0
_SHOT_VELOCITY_Z = 5.5

_FIRST_ROW_POSE = Transform3d(-0.22, 0, 0.35, Rotation3d())
_SECOND_ROW_POSE = Transform3d(-0.08, 0, 0.3, Rotation3d())
_THIRD_ROW_POSE = Transform3d(0.06, 0, 0.25, Rotation3d())
_SHOT_ORIGIN = Transform3d(0.2, 0, 0.5, Rotation3d())


def _basic_parabola(start: Pose3d) -> list[Pose3d]:
    poses = [start]
    t = 0.0
    current_pose = start
    while poses[-1].z > 0:
        delta_x = _SHOT_VELOCITY_X * _SHOT_DT
        delta_z = _SHOT_VELOCITY_Z * _SHOT_DT - 0.5 * 9.8 * ((t + _SHOT_DT) ** 2 - t**2)
        current_pose = current_pose + Transform3d(delta_x, 0, delta_z, Rotation3d())
        poses.append(current_pose)
        t += _SHOT_DT
    return poses


def _fuel_row(base: Pose3d) -> list[Pose3d]:
    offset = Transform3d(0, 0.15, 0, Rotation3d())
    return [base + offset.inverse(), base, base + offset]


class FuelSim:
    """Visualizes the robot's fuel load and shots. All state is class-level."""

    _table = telemetry.get_table("FuelSim")
    _mode: ClassVar[_Mode | None] = None
    _is_paused: ClassVar[bool] = False
    _rows_of_fuel: ClassVar[float] = 3.0

    feeder_volts_supplier: ClassVar[Callable[[], float]] = lambda: 0.0
    """Fetches the input voltage of the feeder."""

    intake_launcher_volts_supplier: ClassVar[Callable[[], float]] = lambda: 0.0
    """Fetches the input voltage of the intake launcher."""

    robot_pose_supplier: ClassVar[Callable[[], Pose2d]] = Pose2d
    """Fetches the robot pose."""

    @classmethod
    def periodic(cls) -> None:
        """Updates the fuel sim."""
        cls._update_mode()
        cls._update_visualization()

    @classmethod
    def _update_mode(cls) -> None:
        intake_launcher_volts = cls.intake_launcher_volts_supplier()
        feeder_volts = cls.feeder_volts_supplier()
        cls._is_paused = False
        if cls._mode is not None:
            cls._table.log("mode", cls._mode.name)
        if intake_launcher_volts > 0 and feeder_volts > 0:
            cls._mode = _Mode.SHOOT
        elif intake_launcher_volts < 0 and feeder_volts > 0:
            cls._mode = _Mode.OUTTAKE
        elif intake_launcher_volts > 0 and feeder_volts < 0:
            cls._mode = _Mode.INTAKE
        else:
            cls._is_paused = True

    @classmethod
    def _update_visualization(cls) -> None:
        robot_pose = Pose3d(cls.robot_pose_supplier())
        table = cls._table

        if cls._mode is _Mode.SHOOT and cls._rows_of_fuel > 0 and not cls._is_paused:
            parabola = _basic_parabola(robot_pose + _SHOT_ORIGIN)
        else:
            parabola = []
        table.log("ParabolaFuel", parabola, element_type=Pose3d)

        if not cls._is_paused:
            cls._rows_of_fuel += 0.04 if cls._mode is _Mode.INTAKE else -0.04
            cls._rows_of_fuel = min(max(cls._rows_of_fuel, 0.0), 3.0)

        rows = cls._rows_of_fuel
        for key, threshold, offset in (
            ("Row1Fuel", 1, _FIRST_ROW_POSE),
            ("Row2Fuel", 2, _SECOND_ROW_POSE),
            ("Row3Fuel", 3, _THIRD_ROW_POSE),
        ):
            poses = _fuel_row(robot_pose + offset) if rows >= threshold else []
            table.log(key, poses, element_type=Pose3d)
