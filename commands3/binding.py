# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""Represents a single command binding - the scope, type, and command it ties together."""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

import hal

from . import robot_state_fetcher

if TYPE_CHECKING:
    from .command import Command
    from .scheduler import Scheduler

__all__ = [
    "AUTONOMOUS_MODE_SCOPE",
    "GLOBAL_SCOPE",
    "TELEOP_MODE_SCOPE",
    "UTILITY_MODE_SCOPE",
    "AutonomousMode",
    "Binding",
    "BindingScope",
    "BindingType",
    "ForCommand",
    "ForOpmode",
    "GlobalScope",
    "RobotModeScope",
    "TeleopMode",
    "UtilityMode",
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

    #: Attempts to schedule (fork) a command on every poll where the signal
    #: is high. Runs until it completes or is interrupted.
    SCHEDULE_WHILE_HIGH = enum.auto()

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
class ForOpmode(BindingScope):
    """A binding scoped to a running opmode."""

    opmode_id: int

    def active(self) -> bool:
        return robot_state_fetcher.get_fetcher().get_opmode_id() == self.opmode_id


class RobotModeScope(BindingScope):
    """
    Base class for scopes tied to a robot mode rather than any particular
    opmode. These come into play when robot programs are using commands v3
    but not opmodes.
    """

    #: The robot mode this scope is active during.
    mode: hal.RobotMode

    def active(self) -> bool:
        return robot_state_fetcher.get_fetcher().get_robot_mode() == self.mode


class AutonomousMode(RobotModeScope):
    """A binding scoped to the autonomous robot mode, but not any particular opmode."""

    mode = hal.RobotMode.AUTONOMOUS


class TeleopMode(RobotModeScope):
    """A binding scoped to the teleop robot mode, but not any particular opmode."""

    mode = hal.RobotMode.TELEOPERATED


class UtilityMode(RobotModeScope):
    """A binding scoped to the utility robot mode, but not any particular opmode."""

    mode = hal.RobotMode.UTILITY


#: Shared ``AutonomousMode`` instance.
AUTONOMOUS_MODE_SCOPE = AutonomousMode()

#: Shared ``TeleopMode`` instance.
TELEOP_MODE_SCOPE = TeleopMode()

#: Shared ``UtilityMode`` instance.
UTILITY_MODE_SCOPE = UtilityMode()

# There is no scope for the "disabled" mode, since it would interfere with
# the global scope.
_ROBOT_MODE_SCOPES: dict[hal.RobotMode, BindingScope] = {
    hal.RobotMode.AUTONOMOUS: AUTONOMOUS_MODE_SCOPE,
    hal.RobotMode.TELEOPERATED: TELEOP_MODE_SCOPE,
    hal.RobotMode.UTILITY: UTILITY_MODE_SCOPE,
}


def create_narrowest_scope(scheduler: Scheduler) -> BindingScope:
    """
    Creates the narrowest scope available right now: scoped to the
    currently-running command if there is one, else to the currently
    selected opmode if there is one, else to the current robot mode, else
    the global scope.
    """
    current_command = scheduler.current_command()

    if current_command is not None:
        # Commands are the narrowest scope, so prioritize them first.
        return ForCommand(scheduler, current_command)

    fetcher = robot_state_fetcher.get_fetcher()
    current_opmode_id = fetcher.get_opmode_id()

    if current_opmode_id != 0:
        # Opmodes are more specific than general robot mode bindings.
        return ForOpmode(current_opmode_id)

    # Not in a command and not in an opmode. Use a robot mode scope, if
    # applicable, or fall back to the global scope if the robot is disabled
    # or in an unrecognized mode.
    return _ROBOT_MODE_SCOPES.get(fetcher.get_robot_mode(), GLOBAL_SCOPE)
