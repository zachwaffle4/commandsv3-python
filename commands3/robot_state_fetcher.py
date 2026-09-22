# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Looks up the current state of the robot - which opmode is selected, which
robot mode it belongs to, and whether the robot is enabled. The default
implementation reads from the driver station; ``set_fetcher()`` lets tests
substitute a fake one instead of hooking into driver station simulation.
"""

from __future__ import annotations

import abc

import hal
import wpilib

__all__ = [
    "DriverStationRobotStateFetcher",
    "RobotStateFetcher",
    "get_fetcher",
    "set_fetcher",
]


class RobotStateFetcher(abc.ABC):
    """Interface for fetching information about the state of the robot."""

    @abc.abstractmethod
    def get_opmode_id(self) -> int:
        raise NotImplementedError

    @abc.abstractmethod
    def get_opmode_name(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def get_robot_mode(self) -> hal.RobotMode:
        raise NotImplementedError

    @abc.abstractmethod
    def is_enabled(self) -> bool:
        raise NotImplementedError


class DriverStationRobotStateFetcher(RobotStateFetcher):
    """Reads the current robot state from the driver station."""

    def get_opmode_id(self) -> int:
        return wpilib.RobotState.get_opmode_id()

    def get_opmode_name(self) -> str:
        return wpilib.RobotState.get_opmode()

    def get_robot_mode(self) -> hal.RobotMode:
        return wpilib.RobotState.get_robot_mode()

    def is_enabled(self) -> bool:
        return wpilib.RobotState.is_enabled()


_fetcher: RobotStateFetcher | None = None


def get_fetcher() -> RobotStateFetcher:
    """Gets the current fetcher, defaulting to a ``DriverStationRobotStateFetcher``."""
    global _fetcher
    if _fetcher is None:
        _fetcher = DriverStationRobotStateFetcher()

    assert _fetcher is not None
    return _fetcher


def set_fetcher(fetcher: RobotStateFetcher | None) -> None:
    """Replaces the fetcher used by ``get_fetcher()``. Intended for tests."""
    global _fetcher
    _fetcher = fetcher
