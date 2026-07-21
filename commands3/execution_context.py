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
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from .command import Command
    from . import CommandState

__all__ = ["mounted", "current_state", "current_command", "require_current_state"]

_stack: list[CommandState] = []


@contextlib.contextmanager
def mounted(state: CommandState) -> Iterator[None]:
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
