# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
The primitives commands use to yield control, wait, and compose with other
commands.

A command's body is an ``async def`` function. Within it, ``await
yield_()`` cedes control back to the scheduler for one tick; everything else
here (``wait``, ``wait_until``, ``park``, ``fork``, ``await_``,
``await_all``, ``await_any``) is built on top of that single primitive.

These are free functions rather than methods on an object, so a command
body can call them directly:

.. code-block:: python

    async def drive_forward():
        while not at_target():
            drive.set(0.5)
            await yield_()
        drive.stop()

``yield``/``await`` are Python keywords, hence the trailing underscore on
``yield_()`` and ``await_()``.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from typing import TYPE_CHECKING

import wpilib
import wpimath.units

from . import execution_context as _ec
from .conflict_detector import throw_if_conflicts

if TYPE_CHECKING:
    from .command import Command

__all__ = [
    "yield_",
    "wait",
    "wait_until",
    "park",
    "fork",
    "await_",
    "await_all",
    "await_any",
]


class _YieldTick:
    """Awaitable that suspends a command for exactly one scheduler tick."""

    __slots__ = ()

    def __await__(self):
        yield
        return True


_YIELD_TICK = _YieldTick()


def yield_() -> _YieldTick:
    """Suspends the current command until the next scheduler tick."""
    return _YIELD_TICK


async def wait(seconds: wpimath.units.seconds) -> None:
    """
    Waits for the given duration to elapse before returning. Returns
    immediately if ``seconds`` is zero or negative.

    The resolution of the wait is equal to however often the scheduler
    driving this command is run; a wait duration that isn't a clean multiple
    of the tick period is rounded up to the next tick.
    """
    timer = wpilib.Timer()
    timer.start()
    while not timer.has_elapsed(seconds):
        await yield_()


async def wait_until(condition: Callable[[], bool]) -> None:
    """Waits until ``condition`` returns ``True`` before returning."""
    while not condition():
        await yield_()


async def park() -> None:
    """
    Suspends the current command forever. No code after ``await park()``
    will run; a parked command never completes on its own and must be
    canceled or interrupted from outside.
    """
    while True:
        await yield_()


def fork(*commands: Command) -> None:
    """
    Schedules one or more commands to run alongside the current command and
    returns immediately, without waiting for them to complete.

    The forked commands are tied to the current command's lifetime: they're
    canceled automatically if the current command is canceled or completes
    first. To fork and later wait for completion, use ``await_()``/
    ``await_all()`` afterward.

    :raises ValueError: if any of the given commands require the same
        mechanism as another.
    :raises RuntimeError: if called outside a command currently being run
        by a ``Scheduler``.
    """
    state = _ec.require_current_state()

    throw_if_conflicts(commands)

    for command in commands:
        state.scheduler.schedule(command)


async def await_(command: Command) -> None:
    """
    Schedules ``command`` (if it isn't already scheduled or running) and
    suspends the current command until it completes.
    """
    state = _ec.require_current_state()

    state.scheduler.schedule(command)
    while state.scheduler.is_scheduled_or_running(command):
        await yield_()


async def await_all(commands: Collection[Command]) -> None:
    """
    Schedules ``commands`` (any not already scheduled or running) and
    suspends the current command until every one of them has completed.

    :raises ValueError: if any of the given commands require the same
        mechanism as another.
    """
    state = _ec.require_current_state()

    throw_if_conflicts(commands)

    for command in commands:
        state.scheduler.schedule(command)

    while any(state.scheduler.is_scheduled_or_running(command) for command in commands):
        await yield_()


async def await_any(commands: Collection[Command]) -> None:
    """
    Schedules ``commands`` (any not already scheduled or running) and
    suspends the current command until any one of them completes, then
    cancels the rest.

    :raises ValueError: if any of the given commands require the same
        mechanism as another.
    """
    state = _ec.require_current_state()

    throw_if_conflicts(commands)

    for command in commands:
        state.scheduler.schedule(command)

    while all(state.scheduler.is_scheduled_or_running(command) for command in commands):
        await yield_()

    for command in commands:
        state.scheduler.cancel(command)
