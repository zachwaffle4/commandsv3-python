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
from dataclasses import dataclass
from typing import TYPE_CHECKING

import wpilib
import wpimath.units

from . import execution_context as _ec
from .conflict_detector import throw_if_conflicts
from .exceptions import ForkFailed

if TYPE_CHECKING:
    from .command import Command
    from .scheduler import CommandState, Scheduler, ScheduleResult

__all__ = [
    "ForkResult",
    "all_of",
    "any_of",
    "await_",
    "fork",
    "park",
    "wait",
    "wait_until",
    "yield_",
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


@dataclass(frozen=True)
class ForkResult:
    """
    The outcome of a ``fork()``/``await_()``/``all_of()``/``any_of()`` call.

    Forking is all-or-nothing: if any of the given commands can't be
    scheduled, none of them are, and this describes which ones failed and
    why. By default a failure doesn't produce one of these at all - it
    raises ``ForkFailed`` and takes the whole composition down with it. Pass
    ``cancel_on_failure=False`` to get the result back and handle it
    yourself.

    :ivar scheduler: the scheduler the commands were forked on.
    :ivar forked_commands: the commands that were successfully forked.
    :ivar failed_commands: a ``ScheduleResult`` per command that couldn't be
        forked, explaining why.
    """

    scheduler: Scheduler
    forked_commands: tuple[Command, ...]
    failed_commands: tuple[ScheduleResult, ...]

    @property
    def successful(self) -> bool:
        """Whether every command was forked."""
        return not self.failed_commands

    @property
    def failed(self) -> bool:
        """Whether at least one command couldn't be forked."""
        return bool(self.failed_commands)

    @property
    def partial_success(self) -> bool:
        """
        Whether at least one command was forked *and* at least one failed.

        This can happen when a child immediately schedules a grandchild of a
        higher priority than a later sibling that shares its requirements -
        something no up-front check can predict.
        """
        return bool(self.forked_commands) and bool(self.failed_commands)

    async def await_completion(self) -> None:
        """
        Suspends until every successfully-forked command has finished.

        Unlike forking and then awaiting, this only waits on the commands
        that are still running, so it won't re-schedule one that already
        completed. Does nothing if no commands were forked.
        """
        for command in self.forked_commands:
            while self.scheduler.is_scheduled_or_running(command):
                await yield_()


def _check_all_forkable(
    state: CommandState, commands: Collection[Command], *, cancel_on_failure: bool
) -> ForkResult:
    # Checks that every command could be forked, before any of them is.
    # Conflicts *within* the batch are a bug in the calling code rather than
    # a runtime condition, so those raise instead of producing a result.
    throw_if_conflicts(commands)

    schedulable: list[Command] = []
    unschedulable: list[ScheduleResult] = []
    for command in commands:
        result = state.scheduler.is_schedulable(command)
        if result.successful:
            schedulable.append(command)
        else:
            unschedulable.append(result)

    return _finish(
        ForkResult(state.scheduler, tuple(schedulable), tuple(unschedulable)),
        cancel_on_failure=cancel_on_failure,
    )


def _do_fork(
    state: CommandState, commands: Collection[Command], *, cancel_on_failure: bool
) -> ForkResult:
    # The actual scheduling pass. Separate from _check_all_forkable because a
    # child can immediately schedule a grandchild that conflicts with a later
    # sibling, which the up-front check can't see coming. A partial success
    # can't be rolled back - the commands that did start have already
    # affected the robot - so the choice is to cancel the composition or let
    # user code deal with it.
    forked: list[Command] = []
    failed: list[ScheduleResult] = []
    for command in commands:
        result = state.scheduler.schedule(command)
        if result.successful:
            forked.append(command)
        else:
            failed.append(result)

    return _finish(
        ForkResult(state.scheduler, tuple(forked), tuple(failed)),
        cancel_on_failure=cancel_on_failure,
    )


def _finish(result: ForkResult, *, cancel_on_failure: bool) -> ForkResult:
    if result.failed and cancel_on_failure:
        raise ForkFailed(result)
    return result


def fork(*commands: Command, cancel_on_failure: bool = True) -> ForkResult:
    """
    Schedules one or more commands to run alongside the current command and
    returns immediately, without waiting for them to complete.

    The forked commands are tied to the current command's lifetime: they're
    canceled automatically if the current command is canceled or completes
    first. To fork and later wait for completion, use the returned result's
    ``await_completion()``, or ``await_()``/``all_of()`` afterward.

    Forking is all-or-nothing: if any command can't be scheduled, none of
    them are.

    Closest ``asyncio`` analog: ``asyncio.create_task()`` - but there's no
    ``Task`` object returned, and the forked commands are scoped to the
    parent the way a structured-concurrency task group would be, rather than
    running independently until explicitly canceled.

    :param cancel_on_failure: when true (the default), a command that can't
        be forked raises ``ForkFailed``, canceling this command and the whole
        composition it belongs to. Set it false to get a failed
        ``ForkResult`` back and recover in the command body instead.
    :raises ValueError: if any of the given commands require the same
        mechanism as another.
    :raises RuntimeError: if called outside a command currently being run
        by a ``Scheduler``.
    :raises ForkFailed: if a command couldn't be forked and
        ``cancel_on_failure`` is true.
    """
    state = _ec.require_current_state()

    check = _check_all_forkable(state, commands, cancel_on_failure=cancel_on_failure)
    if check.failed:
        return check

    return _do_fork(state, commands, cancel_on_failure=cancel_on_failure)


async def await_(command: Command, *, cancel_on_failure: bool = True) -> ForkResult:
    """
    Schedules ``command`` (if it isn't already scheduled or running) and
    suspends the current command until it completes.

    Closest ``asyncio`` analog: awaiting a single ``Task``.

    :param cancel_on_failure: see ``fork()``.
    :raises ForkFailed: if the command couldn't be scheduled and
        ``cancel_on_failure`` is true.
    """
    state = _ec.require_current_state()

    check = _check_all_forkable(state, (command,), cancel_on_failure=cancel_on_failure)
    if check.failed:
        return check

    # No siblings, so no chance of the sibling conflict _do_fork() guards
    # against.
    state.scheduler.schedule(command)

    while state.scheduler.is_scheduled_or_running(command):
        # A one-shot command runs to completion within the schedule call
        # above, leaving nothing to await.
        await yield_()

    return ForkResult(state.scheduler, (command,), ())


async def all_of(
    commands: Collection[Command], *, cancel_on_failure: bool = True
) -> ForkResult:
    """
    Schedules ``commands`` (any not already scheduled or running) and
    suspends the current command until every one of them has completed.

    Closest ``asyncio`` analog: ``asyncio.gather(*commands)`` - but there
    are no return values to collect, since a ``Command``'s body doesn't
    produce one.

    :param cancel_on_failure: see ``fork()``.
    :raises ValueError: if any of the given commands require the same
        mechanism as another.
    :raises ForkFailed: if a command couldn't be scheduled and
        ``cancel_on_failure`` is true.
    """
    state = _ec.require_current_state()

    check = _check_all_forkable(state, commands, cancel_on_failure=cancel_on_failure)
    if check.failed:
        return check

    result = _do_fork(state, commands, cancel_on_failure=cancel_on_failure)
    if result.failed:
        return result

    while any(state.scheduler.is_scheduled_or_running(command) for command in commands):
        await yield_()

    return result


async def any_of(
    commands: Collection[Command], *, cancel_on_failure: bool = True
) -> ForkResult:
    """
    Schedules ``commands`` (any not already scheduled or running) and
    suspends the current command until any one of them completes, then
    cancels the rest.

    Closest ``asyncio`` analog: ``asyncio.wait(commands,
    return_when=asyncio.FIRST_COMPLETED)`` followed by canceling the
    pending ones.

    :param cancel_on_failure: see ``fork()``.
    :raises ValueError: if any of the given commands require the same
        mechanism as another.
    :raises ForkFailed: if a command couldn't be scheduled and
        ``cancel_on_failure`` is true.
    """
    state = _ec.require_current_state()

    check = _check_all_forkable(state, commands, cancel_on_failure=cancel_on_failure)
    if check.failed:
        return check

    result = _do_fork(state, commands, cancel_on_failure=cancel_on_failure)
    if result.failed:
        return result

    while all(state.scheduler.is_scheduled_or_running(command) for command in commands):
        await yield_()

    # At least one command exited; cancel the rest.
    for command in commands:
        state.scheduler.cancel(command)

    return result
