# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
The primitives commands use to yield control, wait, and compose with other
commands.

A command's body is an ``async def`` function. Within it, ``await
yield_()`` cedes control back to the scheduler for one tick; everything else
here (``wait``, ``wait_until``, ``park``, ``fork``, ``await_``, ``all_of``,
``any_of``) is built on top of that single primitive.

These read a bit like ``asyncio``'s task-composition primitives
(``fork`` ~ ``asyncio.create_task``, ``await_`` ~ awaiting a single task,
``all_of`` ~ ``asyncio.gather``, ``any_of`` ~ ``asyncio.wait(...,
return_when=FIRST_COMPLETED)``), which may help if that's a familiar
starting point - but the resemblance is surface-level. There's no real
concurrency here: the ``Scheduler`` drives every command's coroutine itself,
one tick at a time, so plain ``asyncio.sleep()``/``asyncio.gather()`` etc.
won't interact with it at all. Mechanism ownership/conflict checking is also
specific to this framework and has no ``asyncio`` equivalent.

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
    "all_of",
    "any_of",
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

    Closest ``asyncio`` analog: ``asyncio.sleep()`` - but this advances with
    the scheduler's own clock, not a real timer, so it only progresses while
    the scheduler is being run.
    """
    timer = wpilib.Timer()
    timer.start()
    while not timer.has_elapsed(seconds):
        await yield_()


async def wait_until(condition: Callable[[], bool]) -> None:
    """
    Waits until ``condition`` returns ``True`` before returning.

    No direct ``asyncio`` analog - closest is polling a condition inside a
    loop of ``await asyncio.sleep(0)``, which is essentially what this does.
    """
    while not condition():
        await yield_()


async def park() -> None:
    """
    Suspends the current command forever. No code after ``await park()``
    will run; a parked command never completes on its own and must be
    canceled or interrupted from outside.

    No direct ``asyncio`` analog - closest is an ``asyncio.Event`` that's
    never set, awaited with no timeout.
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
    ``all_of()`` afterward.

    Closest ``asyncio`` analog: ``asyncio.create_task()`` - but there's no
    ``Task`` object returned, and the forked commands are scoped to the
    parent the way a structured-concurrency task group would be, rather than
    running independently until explicitly canceled.

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

    Closest ``asyncio`` analog: awaiting a single ``Task``.
    """
    state = _ec.require_current_state()

    state.scheduler.schedule(command)
    while state.scheduler.is_scheduled_or_running(command):
        await yield_()


async def all_of(commands: Collection[Command]) -> None:
    """
    Schedules ``commands`` (any not already scheduled or running) and
    suspends the current command until every one of them has completed.

    Closest ``asyncio`` analog: ``asyncio.gather(*commands)`` - but there
    are no return values to collect, since a ``Command``'s body doesn't
    produce one.

    :raises ValueError: if any of the given commands require the same
        mechanism as another.
    """
    state = _ec.require_current_state()

    throw_if_conflicts(commands)

    for command in commands:
        state.scheduler.schedule(command)

    while any(state.scheduler.is_scheduled_or_running(command) for command in commands):
        await yield_()


async def any_of(commands: Collection[Command]) -> None:
    """
    Schedules ``commands`` (any not already scheduled or running) and
    suspends the current command until any one of them completes, then
    cancels the rest.

    Closest ``asyncio`` analog: ``asyncio.wait(commands,
    return_when=asyncio.FIRST_COMPLETED)`` followed by canceling the
    pending ones.

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
