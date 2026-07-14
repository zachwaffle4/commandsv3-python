# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A descriptor for a single command-based opmode, exposing triggers for its selection and enabled state."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wpilib

from . import opmode_fetcher
from .trigger import Trigger

if TYPE_CHECKING:
    from .command import Command
    from .mechanism import Mechanism

__all__ = ["OpModeTriggers"]


class OpModeTriggers:
    """
    Returned by ``CommandRobot.create_*_opmode()`` and the module-level
    ``create_*_opmode()`` functions to configure behavior for one opmode:
    which commands run when it's selected, enabled, or disabled, and its
    default commands.
    """

    def __init__(self, name: str) -> None:
        """Creates a descriptor for the opmode named ``name``, matching the name it was registered under."""
        self._name = name
        self._loaded = Trigger(
            lambda: opmode_fetcher.get_fetcher().get_opmode_name() == name
        )
        self._enabled = self._loaded.and_(wpilib.RobotState.is_enabled)
        self._disabled = self._loaded.and_(wpilib.RobotState.is_disabled)

    def loaded(self) -> Trigger:
        """True when this opmode is currently loaded on the Driver Station."""
        return self._loaded

    def enabled(self, other: Trigger | None = None) -> Trigger:
        """
        True when this opmode is loaded and the robot is enabled. If
        ``other`` is given, the result also requires ``other`` to be
        active.
        """
        if other is None:
            return self._enabled
        return self._enabled.and_(other)

    def disabled(self, other: Trigger | None = None) -> Trigger:
        """
        True when this opmode is loaded and the robot is disabled. If
        ``other`` is given, the result also requires ``other`` to be
        active.
        """
        if other is None:
            return self._disabled
        return self._disabled.and_(other)

    def set_default_command(self, mechanism: Mechanism, command: Command) -> None:
        """Sets the default command for a mechanism during this opmode."""
        from .scheduler import Scheduler

        Scheduler.get_default().set_default_command_for_opmode(
            self._name, mechanism, command
        )

    def remove_default_command(self, mechanism: Mechanism) -> None:
        """Removes the default command for a mechanism during this opmode."""
        from .scheduler import Scheduler

        Scheduler.get_default().remove_default_command(self._name, mechanism)
