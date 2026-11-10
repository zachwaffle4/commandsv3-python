# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A loop that runs a set of callbacks each time it's polled, supporting adding and removing them."""

from __future__ import annotations

import inspect
import weakref
from collections.abc import Callable
from typing import Any

import wpilib

__all__ = ["EventLoop"]

_Action = Callable[[], None]


def _key_of(action: _Action) -> tuple[Any, ...]:
    # A bound method is a fresh object on every attribute access, so identity
    # of the method object can't be used. Its owner and underlying function
    # are what make two bound methods "the same" callback.
    if inspect.ismethod(action):
        return (id(action.__self__), action.__func__)
    return (id(action),)


class _Entry:
    """A bound action, held strongly, weakly, or both."""

    __slots__ = ("strong", "weak")

    def __init__(self) -> None:
        self.strong: _Action | None = None
        self.weak: Callable[[], _Action | None] | None = None

    def get(self) -> _Action | None:
        if self.strong is not None:
            return self.strong
        return self.weak() if self.weak is not None else None


class EventLoop:
    """
    Runs a set of zero-argument callbacks each time ``poll()`` is called.
    Callbacks are run in the order they were bound; binding the same
    callback twice has no additional effect.
    """

    def __init__(self) -> None:
        self._native = wpilib.EventLoop()
        # dict, not set/list, for insertion-ordered "no duplicates" semantics.
        self._bindings: dict[tuple[Any, ...], _Entry] = {}
        self._running = False
        self._native.bind(self._run_all)

    def bind(self, action: _Action) -> None:
        """
        Adds ``action`` to the set of callbacks run on each ``poll()``. The
        loop keeps a reference to it, which prevents it from being garbage
        collected; see ``bind_weak()`` if that's a concern.
        """
        if self._running:
            raise RuntimeError("Cannot bind EventLoop while it is running")
        self._entry_for(action).strong = action

    def bind_weak(self, action: _Action) -> None:
        """
        Like ``bind()``, but the loop only holds a weak reference, so
        ``action`` can still be garbage collected if nothing else refers to
        it. A collected action silently stops running. If ``action`` is
        already bound, this has no additional effect.
        """
        if self._running:
            raise RuntimeError("Cannot bind EventLoop while it is running")
        entry = self._entry_for(action)
        if entry.weak is None:
            entry.weak = (
                weakref.WeakMethod(action)
                if inspect.ismethod(action)
                else weakref.ref(action)
            )

    def is_bound(self, action: _Action) -> bool:
        """Whether ``action`` is currently bound and hasn't been garbage collected."""
        entry = self._bindings.get(_key_of(action))
        return entry is not None and entry.get() is not None

    def unbind(self, action: _Action) -> None:
        """Removes ``action`` from the set of callbacks. No effect if it wasn't bound."""
        if self._running:
            raise RuntimeError("Cannot unbind EventLoop while it is running")
        self._bindings.pop(_key_of(action), None)

    def poll(self) -> None:
        """Runs every currently-bound callback, in the order they were bound."""
        self._native.poll()

    def clear(self) -> None:
        """Removes every bound callback."""
        if self._running:
            raise RuntimeError("Cannot clear EventLoop while it is running")
        self._bindings.clear()

    def _entry_for(self, action: _Action) -> _Entry:
        key = _key_of(action)
        entry = self._bindings.get(key)
        if entry is not None and entry.get() is None:
            # The previous owner was collected and its id has been reused.
            # Drop the stale entry so the new action goes to the end of the
            # run order like any fresh binding.
            del self._bindings[key]
            entry = None
        if entry is None:
            entry = self._bindings[key] = _Entry()
        return entry

    def _run_all(self) -> None:
        self._running = True
        try:
            # Snapshot before iterating: mutating a dict while iterating it
            # raises in Python regardless of our own guard - copy first so
            # *our* RuntimeError (from bind()/unbind() above) is what a
            # misbehaving action sees, not a generic Python one.
            #
            # Weak entries are resolved here, once, and collected ones are
            # dropped. Doing that cleanup in a weakref callback instead would
            # mutate the dict at arbitrary GC points, including mid-snapshot.
            actions: list[_Action] = []
            dead: list[tuple[Any, ...]] = []
            for key, entry in list(self._bindings.items()):
                action = entry.get()
                if action is None:
                    dead.append(key)
                else:
                    actions.append(action)
            for key in dead:
                del self._bindings[key]

            for action in actions:
                action()
        finally:
            self._running = False
