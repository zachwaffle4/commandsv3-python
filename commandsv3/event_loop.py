# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A loop that runs a set of callbacks each time it's polled, supporting adding and removing them."""

from __future__ import annotations

from collections.abc import Callable

import wpilib

__all__ = ["EventLoop"]

_Action = Callable[[], None]


class EventLoop:
    """
    Runs a set of zero-argument callbacks each time ``poll()`` is called.
    Callbacks are run in the order they were bound; binding the same
    callback twice has no additional effect.
    """

    def __init__(self) -> None:
        self._native = wpilib.EventLoop()
        # dict, not set/list, for insertion-ordered "no duplicates" semantics.
        self._bindings: dict[_Action, None] = {}
        self._running = False
        self._native.bind(self._run_all)

    def bind(self, action: _Action) -> None:
        """Adds ``action`` to the set of callbacks run on each ``poll()``."""
        if self._running:
            raise RuntimeError("Cannot bind EventLoop while it is running")
        self._bindings[action] = None

    def unbind(self, action: _Action) -> None:
        """Removes ``action`` from the set of callbacks. No effect if it wasn't bound."""
        if self._running:
            raise RuntimeError("Cannot unbind EventLoop while it is running")
        self._bindings.pop(action, None)

    def poll(self) -> None:
        """Runs every currently-bound callback, in the order they were bound."""
        self._native.poll()

    def clear(self) -> None:
        """Removes every bound callback."""
        if self._running:
            raise RuntimeError("Cannot clear EventLoop while it is running")
        self._bindings.clear()

    def _run_all(self) -> None:
        self._running = True
        try:
            # Snapshot before iterating: mutating a dict while iterating it
            # raises in Python regardless of our own guard - copy first so
            # *our* RuntimeError (from bind()/unbind() above) is what a
            # misbehaving action sees, not a generic Python one.
            for action in list(self._bindings.keys()):
                action()
        finally:
            self._running = False
