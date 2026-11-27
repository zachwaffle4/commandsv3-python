# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Tracks which command is currently executing, so that helpers like ``fork()``
and ``await_()`` can find the scheduler driving the currently-running
command without needing it passed in explicitly.

A single shared stack is used for the whole process rather than one per
``Scheduler``, since ``commandsv3`` is a single-threaded framework and only
one command is ever actually executing at a time.
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import CommandState
    from .command import Command
    from .scheduler import Scheduler

__all__ = [
    "cancels_on_fork_failure_by_default",
    "cleaning_up",
    "current_command",
    "current_state",
    "has_mounted_command",
    "has_mounted_command_of",
    "is_mounted",
    "mounted",
    "require_current_scheduler",
    "require_current_state",
    "sideloading",
]

_stack: list[CommandState] = []

# Schedulers currently running a sideload, innermost last. A sideload isn't a
# command, so it has no ``CommandState`` to put on ``_stack``; this holds just
# enough for ``fork()`` and friends to find the scheduler to use.
_sideload_schedulers: list[Scheduler] = []

# How many canceled commands' cleanup is running right now. See cleaning_up().
_cleanup_depth = 0


@contextlib.contextmanager
def cleaning_up() -> Generator[None]:
    """
    Marks the cleanup of a canceled command (its ``finally`` blocks, run by
    throwing ``CommandCancelled`` into it) as executing for the duration of
    the ``with`` block.

    Cleanup runs detached from whatever command caused the cancellation: it
    isn't that command's work, and the canceled command itself is no longer
    running. So ``current_state()`` is ``None`` - whatever the cleanup
    schedules is queued as a top-level command - and the coroutine primitives
    refuse to run. ``is_mounted()`` still sees the real stack, so the
    scheduler still knows which coroutines can't be thrown into.
    """
    global _cleanup_depth
    _cleanup_depth += 1
    try:
        yield
    finally:
        _cleanup_depth -= 1


@contextlib.contextmanager
def mounted(state: CommandState) -> Generator[None]:
    """
    Marks ``state`` as the currently-executing command for the duration of
    the ``with`` block. Guaranteed to be un-marked afterward, even if the
    command's coroutine raises.
    """
    _stack.append(state)
    try:
        yield
    finally:
        _stack.pop()


@contextlib.contextmanager
def sideloading(scheduler: Scheduler) -> Generator[None]:
    """
    Marks a sideload driven by ``scheduler`` as executing for the duration of
    the ``with`` block. Unlike ``mounted()`` this doesn't make any command
    current: ``current_state()`` stays ``None``, so anything the sideload
    schedules is queued as a top-level command rather than started as a child.
    """
    _sideload_schedulers.append(scheduler)
    try:
        yield
    finally:
        _sideload_schedulers.pop()


def current_state() -> CommandState | None:
    """
    The state of the command currently executing, or ``None`` if none is -
    including while a canceled command's cleanup runs (see ``cleaning_up()``).
    """
    if _cleanup_depth:
        return None
    return _stack[-1] if _stack else None


def has_mounted_command() -> bool:
    """Whether any command is on the stack, even if cleanup is running above it."""
    return bool(_stack)


def current_command() -> Command | None:
    """The command currently executing, or ``None`` if none is."""
    state = current_state()
    return state.command if state is not None else None


def is_mounted(command: Command) -> bool:
    """
    Whether ``command`` is executing right now: the current command, or an
    ancestor of it that's waiting on the stack for the current one to return.
    """
    return any(state.command is command for state in _stack)


def has_mounted_command_of(scheduler: Scheduler) -> bool:
    """Whether any command run by ``scheduler`` is executing right now."""
    return any(state.scheduler is scheduler for state in _stack)


def require_current_state() -> CommandState:
    """
    The state of the command currently executing.

    :raises RuntimeError: if no command is currently executing - these
        primitives (``fork``/``await_``/``all_of``/``any_of``) can
        only be used from within a command that's actually being run by a
        ``Scheduler``.
    """
    state = current_state()
    if state is None:
        raise RuntimeError(
            "commandsv3 coroutine primitives (fork/await_/all_of/any_of) "
            "can only be used by a command currently being run by a Scheduler"
        )
    return state


def require_current_scheduler() -> Scheduler:
    """
    The scheduler driving whatever is currently executing: the running
    command, or a sideload if no command is mounted.

    :raises RuntimeError: if neither a command nor a sideload is executing,
        or if a canceled command's cleanup is.
    """
    if _cleanup_depth:
        raise RuntimeError(
            "commandsv3 coroutine primitives (fork/await_/all_of/any_of) "
            "can't be used in the cleanup of a canceled command. Cleanup can't "
            "suspend; use Scheduler.schedule() to queue a command instead"
        )
    state = current_state()
    if state is not None:
        return state.scheduler
    if _sideload_schedulers:
        return _sideload_schedulers[-1]
    raise RuntimeError(
        "commandsv3 coroutine primitives (fork/await_/all_of/any_of) "
        "can only be used by a command or sideload currently being run by a Scheduler"
    )


def cancels_on_fork_failure_by_default() -> bool:
    """
    Whether a failed fork cancels the caller unless told otherwise. True
    inside a command, so a command that can't start its children doesn't carry
    on in an unexpected state. False inside a sideload, which should get the
    chance to recover; it has no composition to take down.
    """
    return current_state() is not None or not _sideload_schedulers
