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
    "current_command",
    "current_state",
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
    """The state of the command currently executing, or ``None`` if none is."""
    return _stack[-1] if _stack else None


def current_command() -> Command | None:
    """The command currently executing, or ``None`` if none is."""
    state = current_state()
    return state.command if state is not None else None


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

    :raises RuntimeError: if neither a command nor a sideload is executing.
    """
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
