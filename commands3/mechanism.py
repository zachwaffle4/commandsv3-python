# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""Mechanisms: the hardware (or other resources) commands claim exclusive ownership of while running."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .command import (
    LOWEST_PRIORITY,
    Command,
    CommandBody,
    NeedsNameBuilderStage,
    StagedCommandBuilder,
)
from .coroutine import park, yield_
from .scheduler import Scheduler

if TYPE_CHECKING:
    import wpimath.units

__all__ = ["Mechanism"]


class Mechanism:
    """
    Represents a mechanism (or other piece of hardware) that commands can
    require exclusive ownership of. Subclass this for each subsystem on a
    robot - a drivetrain, an arm, an LED strip, and so on.
    """

    def __init__(self, name: str | None = None) -> None:
        """Creates a mechanism named ``name``, defaulting to the subclass's class name."""
        self._name = name or type(self).__name__

    @property
    def name(self) -> str:
        """The mechanism's display name, used in logs and telemetry."""
        return self._name

    def get_registered_scheduler(self) -> Scheduler:
        """The scheduler this mechanism's commands and default command are registered with."""
        return Scheduler.get_default()

    def set_default_command(self, default_command: Command) -> None:
        """Sets the command to run whenever no other command is using this mechanism."""
        self.get_registered_scheduler().set_default_command(self, default_command)

    def get_default_command(self) -> Command | None:
        """The command currently configured to run when nothing else is using this mechanism."""
        return self.get_registered_scheduler().get_default_command_for(self)

    def get_running_commands(self) -> list[Command]:
        """Every currently running command that requires this mechanism."""
        return self.get_registered_scheduler().get_running_commands_for(self)

    def run(self, command_body: CommandBody) -> NeedsNameBuilderStage:
        """Starts building a command that requires this mechanism, with ``command_body`` as its implementation."""
        return StagedCommandBuilder().requiring(self).executing(command_body)

    def run_repeatedly(self, loop_body: Callable[[], None]) -> NeedsNameBuilderStage:
        """Starts building a command that requires this mechanism and calls ``loop_body`` on every tick, forever."""

        async def _looping_body() -> None:
            while True:
                loop_body()
                await yield_()

        return self.run(_looping_body)

    def idle(self) -> Command:
        """A command that claims this mechanism and does nothing until another command takes over."""
        return self.run(park).with_priority(LOWEST_PRIORITY).named(f"{self.name}[IDLE]")

    def idle_for(self, duration: wpimath.units.seconds) -> Command:
        """A command that claims this mechanism and does nothing for the given duration."""
        return self.idle().with_timeout(duration)
