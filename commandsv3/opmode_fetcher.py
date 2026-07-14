# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Looks up which opmode is currently selected. The default implementation
reads from the driver station; ``set_fetcher()`` lets tests substitute a
fake one instead of hooking into driver station simulation.
"""

from __future__ import annotations

import abc

import wpilib

__all__ = ["OpModeFetcher", "DriverStationOpModeFetcher", "get_fetcher", "set_fetcher"]


class OpModeFetcher(abc.ABC):
    """Interface for fetching information about the current opmode."""

    @abc.abstractmethod
    def get_opmode_id(self) -> int:
        raise NotImplementedError

    @abc.abstractmethod
    def get_opmode_name(self) -> str:
        raise NotImplementedError


class DriverStationOpModeFetcher(OpModeFetcher):
    """Reads the current opmode from the driver station."""

    def get_opmode_id(self) -> int:
        return wpilib.RobotState.get_opmode_id()

    def get_opmode_name(self) -> str:
        return wpilib.RobotState.get_opmode()


_fetcher: OpModeFetcher | None = None


def get_fetcher() -> OpModeFetcher | None:
    """Gets the current fetcher, defaulting to a ``DriverStationOpModeFetcher``."""
    global _fetcher
    if _fetcher is None:
        _fetcher = DriverStationOpModeFetcher()
    return _fetcher


def set_fetcher(fetcher: OpModeFetcher) -> None:
    """Replaces the fetcher used by ``get_fetcher()``. Intended for tests."""
    global _fetcher
    _fetcher = fetcher
