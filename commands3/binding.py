# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""Represents a single command binding - the scope, type, and command it ties together."""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import opmode_fetcher

if TYPE_CHECKING:
    from .command import Command
    from .scheduler import Scheduler

__all__ = [
    "Binding",
    "BindingType",
    "BindingScope",
    "GlobalScope",
    "GLOBAL_SCOPE",
    "ForCommand",
    "ForOpMode",
    "create_narrowest_scope",
]


@dataclass(frozen=True)
class Binding:
    """
    Ties a command to the scope it's active in and the type of binding that
    created it (a manual schedule, a default command, a trigger, etc).
    """

    scope: BindingScope
    type: BindingType
    command: Command


class BindingType(enum.Enum):
    """Describes when a command bound to a trigger should run."""

    #: An immediate or manual binding created by calling ``Scheduler.schedule()``
    #: directly, without a trigger.
    IMMEDIATE = enum.auto()

    #: Schedules (forks) a command on a rising edge signal. Runs until it
    #: completes or is interrupted.
    SCHEDULE_ON_RISING_EDGE = enum.auto()

    #: Schedules (forks) a command on a falling edge signal. Runs until it
    #: completes or is interrupted.
    SCHEDULE_ON_FALLING_EDGE = enum.auto()

    #: Schedules (forks) a command on a rising edge signal; canceled on the
    #: next rising edge if still running, otherwise scheduled again.
    TOGGLE_ON_RISING_EDGE = enum.auto()

    #: Schedules (forks) a command on a falling edge signal; canceled on the
    #: next falling edge if still running, otherwise scheduled again.
    TOGGLE_ON_FALLING_EDGE = enum.auto()

    #: Schedules a command on a rising edge signal; canceled on the next
    #: falling edge even if still running.
    RUN_WHILE_HIGH = enum.auto()

    #: Schedules a command on a falling edge signal; canceled on the next
    #: rising edge even if still running.
    RUN_WHILE_LOW = enum.auto()

    #: Continuously attempts to schedule a command as long as the signal
    #: remains high.
    CONTINUOUSLY_SCHEDULE_WHILE_HIGH = enum.auto()

    #: Continuously attempts to schedule a command as long as the signal
    #: remains low.
    CONTINUOUSLY_SCHEDULE_WHILE_LOW = enum.auto()


class BindingScope(abc.ABC):
    """
    A scope for when a binding is live. Bindings tied to a scope must be
    deleted when the scope becomes inactive.
    """

    @abc.abstractmethod
    def active(self) -> bool:
        raise NotImplementedError


class GlobalScope(BindingScope):
    """A global binding scope. Bindings in this scope are always active."""

    def active(self) -> bool:
        return True


#: Shared ``GlobalScope`` instance - bindings in this scope never expire.
GLOBAL_SCOPE = GlobalScope()


@dataclass(frozen=True)
class ForCommand(BindingScope):
    """A binding scoped to the lifetime of a specific command."""

    scheduler: Scheduler
    command: Command

    def active(self) -> bool:
        return self.scheduler.is_running(self.command)


@dataclass(frozen=True)
class ForOpMode(BindingScope):
    """A binding scoped to an opmode."""

    opmode_name: str

    def active(self) -> bool:
        return opmode_fetcher.get_fetcher().get_opmode_name() == self.opmode_name


def create_narrowest_scope(scheduler: Scheduler) -> BindingScope:
    """
    Creates the narrowest scope available right now: scoped to the
    currently-running command if there is one, else to the currently
    selected opmode if there is one, else the global scope.
    """
    current_command = scheduler.current_command()
    current_opmode = opmode_fetcher.get_fetcher().get_opmode_name()

    if current_command is not None:
        return ForCommand(scheduler, current_command)
    elif current_opmode:
        return ForOpMode(current_opmode)
    else:
        return GLOBAL_SCOPE
