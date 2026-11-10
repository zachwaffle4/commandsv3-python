# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Events a ``Scheduler`` emits as commands move through their lifecycle.

Register a listener with ``Scheduler.add_event_listener()`` to receive them.
Events are emitted immediately, as the action happens, so they can see
things the scheduler's other introspection can't: in particular a one-shot
command, which is scheduled, run, and finished inside a single ``run()``,
produces ``Scheduled``, ``Mounted`` and ``Completed`` events.

The classes live in this module rather than being re-exported by name from
``commands3``, because names like ``Canceled`` and ``Completed`` are too
generic to sit at the top level. Import the module::

    from commands3 import scheduler_event

    def on_event(event):
        if isinstance(event, scheduler_event.Canceled):
            print(f"{event.command.name} was canceled")

    scheduler.add_event_listener(on_event)

They are frozen dataclasses, so ``match`` works too::

    match event:
        case scheduler_event.Interrupted(command=c, interrupter=i):
            ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .command import Command
    from .scheduler import FailedScheduleResult

__all__ = [
    "Canceled",
    "Completed",
    "CompletedWithError",
    "ForkFailure",
    "Interrupted",
    "Mounted",
    "Scheduled",
    "SchedulerEvent",
    "Yielded",
]


@dataclass(frozen=True)
class SchedulerEvent:
    """
    Base class of every scheduler event.

    :ivar timestamp_nanos: when the event was emitted, from
        ``wpilib.RobotController.get_time()``, in nanoseconds.
    """

    timestamp_nanos: int = field(kw_only=True)


@dataclass(frozen=True)
class Scheduled(SchedulerEvent):
    """A command was scheduled, whether it's queued or about to start immediately."""

    command: Command


@dataclass(frozen=True)
class Mounted(SchedulerEvent):
    """A command is about to run until it next yields or exits."""

    command: Command


@dataclass(frozen=True)
class Yielded(SchedulerEvent):
    """A command yielded control back to the scheduler and will run again next tick."""

    command: Command


@dataclass(frozen=True)
class Completed(SchedulerEvent):
    """A command ran to completion."""

    command: Command


@dataclass(frozen=True)
class CompletedWithError(SchedulerEvent):
    """
    A command raised an exception. Emitted before any of the command's
    children are canceled, so their ``Canceled`` events come after it.

    :ivar error: the exception the command raised.
    """

    command: Command
    error: BaseException


@dataclass(frozen=True)
class Canceled(SchedulerEvent):
    """
    A command was canceled while it was queued or running. Not emitted for a
    command the scheduler doesn't know about.
    """

    command: Command


@dataclass(frozen=True)
class Interrupted(SchedulerEvent):
    """
    A command was evicted because another command that requires one of the
    same mechanisms was scheduled. A ``Canceled`` event for it follows.

    :ivar interrupter: the command that took its place.
    """

    command: Command
    interrupter: Command


@dataclass(frozen=True)
class ForkFailure(SchedulerEvent):
    """
    A command couldn't fork one or more commands, and was configured to be
    canceled when that happens. Emitted only for the command that attempted
    the fork, not for the ancestors that are canceled along with it.

    :ivar failures: why each command couldn't be scheduled.
    """

    command: Command
    failures: tuple[FailedScheduleResult, ...]
