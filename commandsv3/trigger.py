# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Triggers: conditions that start, stop, or toggle commands based on how a
boolean value changes over time - a button press, a sensor reading, an
opmode being selected, and so on.

``and_``/``or_``/``negate`` compose triggers (``and``/``or``/``not`` are
Python keywords, hence the trailing underscore). ``__and__``/``__or__``/
``__bool__`` are also provided as operator-overload aliases (``a & b`` for
``a.and_(b)``, etc). ``negate()``'s alias is ``__neg__`` (unary
``-trigger``), not ``__invert__`` (``~trigger``).
"""

from __future__ import annotations

import collections
import enum
from collections.abc import Callable
from typing import TYPE_CHECKING

import wpilib
import wpimath
import wpimath.units

from .binding import Binding
from . import BindingType, BindingScope, create_narrowest_scope
from .event_loop import EventLoop

if TYPE_CHECKING:
    from .command import Command
    from .scheduler import Scheduler

__all__ = ["Trigger"]

_Condition = Callable[[], bool]


class _Signal(enum.Enum):
    """Represents the state of a signal. Used instead of a bool for nullity on the first poll."""

    HIGH = enum.auto()
    LOW = enum.auto()


class Trigger:
    """
    A condition, checked once per event loop poll, that can start, stop, or
    toggle commands based on how it changes over time.

    A binding created while a command is running (e.g. ``some_trigger.on_true(...)``
    called from inside a command's body) is scoped to that command's
    lifetime: it's automatically removed, and any command it scheduled
    canceled, once the enclosing command stops running.
    """

    def __init__(
        self,
        condition: _Condition,
        scheduler: Scheduler | None = None,
        loop: EventLoop | None = None,
    ) -> None:
        if scheduler is None:
            from .scheduler import Scheduler

            scheduler = Scheduler.get_default()
        if loop is None:
            loop = scheduler.get_default_event_loop()

        self._condition = condition
        self._loop = loop
        self._scheduler = scheduler
        self._previous_signal: _Signal | None = None
        self._cached_signal: _Signal | None = None
        self._bindings: dict[BindingType, list[Binding]] = collections.defaultdict(list)
        self._bound = True
        self._creation_scope: BindingScope = create_narrowest_scope(scheduler)

        scheduler._add_bound_trigger(self)
        self._loop.bind(self._poll)

    # -- Binding methods ---------------------------------------------------

    def on_true(self, command: Command) -> Trigger:
        """Starts ``command`` whenever the condition changes from false to true."""
        self._add_binding(BindingType.SCHEDULE_ON_RISING_EDGE, command)
        return self

    def on_false(self, command: Command) -> Trigger:
        """Starts ``command`` whenever the condition changes from true to false."""
        self._add_binding(BindingType.SCHEDULE_ON_FALLING_EDGE, command)
        return self

    def while_true(self, command: Command) -> Trigger:
        """Starts ``command`` while the condition is true; cancels it when the condition goes false."""
        self._add_binding(BindingType.RUN_WHILE_HIGH, command)
        return self

    def while_false(self, command: Command) -> Trigger:
        """Starts ``command`` while the condition is false; cancels it when the condition goes true."""
        self._add_binding(BindingType.RUN_WHILE_LOW, command)
        return self

    def retry_while_true(self, command: Command) -> Trigger:
        """Like ``while_true``, but restarts ``command`` if it ends while the condition is still true."""
        self._add_binding(BindingType.CONTINUOUSLY_SCHEDULE_WHILE_HIGH, command)
        return self

    def retry_while_false(self, command: Command) -> Trigger:
        """Like ``while_false``, but restarts ``command`` if it ends while the condition is still false."""
        self._add_binding(BindingType.CONTINUOUSLY_SCHEDULE_WHILE_LOW, command)
        return self

    def toggle_on_true(self, command: Command) -> Trigger:
        """Toggles ``command`` when the condition changes from false to true."""
        self._add_binding(BindingType.TOGGLE_ON_RISING_EDGE, command)
        return self

    def toggle_on_false(self, command: Command) -> Trigger:
        """Toggles ``command`` when the condition changes from true to false."""
        self._add_binding(BindingType.TOGGLE_ON_FALLING_EDGE, command)
        return self

    # -- Composition ---------------------------------------------------

    def get_as_boolean(self) -> bool:
        """
        The state of the trigger as of the most recent event loop poll.
        Always false before the first poll.
        """
        return self._cached_signal == _Signal.HIGH

    def __bool__(self) -> bool:
        """The state of the trigger as of the most recent event loop poll."""
        return self.get_as_boolean()

    def and_(self, condition: _Condition) -> Trigger:
        """A trigger active when both this trigger and ``condition`` are active."""
        return Trigger(
            lambda: self.get_as_boolean() and condition(), self._scheduler, self._loop
        )

    def __and__(self, condition: _Condition) -> Trigger:
        """A trigger active when both this trigger and ``condition`` are active."""
        return self.and_(condition)

    def or_(self, condition: _Condition) -> Trigger:
        """A trigger active when either this trigger or ``condition`` is active."""
        return Trigger(
            lambda: self.get_as_boolean() or condition(), self._scheduler, self._loop
        )

    def __or__(self, condition: _Condition) -> Trigger:
        """A trigger active when either this trigger or ``condition`` is active."""
        return self.or_(condition)

    def negate(self) -> Trigger:
        """The negation of this trigger."""
        return Trigger(lambda: not self.get_as_boolean(), self._scheduler, self._loop)

    def __neg__(self) -> Trigger:
        """The negation of this trigger."""
        return self.negate()

    def debounce(
        self,
        duration: wpimath.units.seconds,
        debounce_type: wpimath.Debouncer.DebounceType = wpimath.Debouncer.DebounceType.RISING,
    ) -> Trigger:
        """A trigger that's active once this trigger has been active for longer than ``duration``."""
        debouncer = wpimath.Debouncer(duration, debounce_type)
        return Trigger(
            lambda: debouncer.calculate(self.get_as_boolean()),
            self._scheduler,
            self._loop,
        )

    def rising_edge(self) -> Trigger:
        """A trigger active for exactly one cycle on this trigger's rising edge."""
        return Trigger(
            lambda: (
                self._cached_signal == _Signal.HIGH
                and self._previous_signal == _Signal.LOW
            ),
            self._scheduler,
            self._loop,
        )

    def falling_edge(self) -> Trigger:
        """A trigger active for exactly one cycle on this trigger's falling edge."""
        return Trigger(
            lambda: (
                self._cached_signal == _Signal.LOW
                and self._previous_signal == _Signal.HIGH
            ),
            self._scheduler,
            self._loop,
        )

    def multi_press(self, press_count: int, duration: wpimath.units.seconds) -> Trigger:
        """A trigger active once this trigger has had ``press_count`` rising edges within ``duration``."""
        if duration <= 0:
            return Trigger(lambda: False, self._scheduler, self._loop)
        if press_count <= 0:
            return Trigger(lambda: True, self._scheduler, self._loop)

        timestamps: collections.deque = collections.deque()
        rising_edge_occurred = False

        def condition() -> bool:
            nonlocal rising_edge_occurred

            if (
                self._cached_signal == _Signal.HIGH
                and self._previous_signal != _Signal.HIGH
            ):
                if not rising_edge_occurred:
                    timestamps.append(wpilib.Timer.get_timestamp())
                    rising_edge_occurred = True
            elif self._cached_signal != _Signal.HIGH:
                rising_edge_occurred = False

            current_time = wpilib.Timer.get_timestamp()
            while timestamps and current_time - timestamps[0] > duration + 1e-9:
                timestamps.popleft()

            return len(timestamps) >= press_count

        return Trigger(condition, self._scheduler, self._loop)

    # -- Polling ---------------------------------------------------

    def _poll(self) -> None:
        # Always checked, regardless of signal change, since bindings may be
        # scoped and those scopes may have gone inactive.
        self._clear_stale_bindings()

        self._previous_signal = self._cached_signal
        self._cached_signal = self._read_signal()

        if self._cached_signal == _Signal.HIGH:
            self._schedule_bindings(BindingType.CONTINUOUSLY_SCHEDULE_WHILE_HIGH)
        elif self._cached_signal == _Signal.LOW:
            self._schedule_bindings(BindingType.CONTINUOUSLY_SCHEDULE_WHILE_LOW)

        if self._cached_signal == self._previous_signal:
            return

        if self._cached_signal == _Signal.HIGH:
            self._schedule_bindings(BindingType.SCHEDULE_ON_RISING_EDGE)
            self._schedule_bindings(BindingType.RUN_WHILE_HIGH)
            self._cancel_bindings(BindingType.RUN_WHILE_LOW)
            self._cancel_bindings(BindingType.CONTINUOUSLY_SCHEDULE_WHILE_LOW)
            self._toggle_bindings(BindingType.TOGGLE_ON_RISING_EDGE)

        if self._cached_signal == _Signal.LOW:
            self._schedule_bindings(BindingType.SCHEDULE_ON_FALLING_EDGE)
            self._schedule_bindings(BindingType.RUN_WHILE_LOW)
            self._cancel_bindings(BindingType.RUN_WHILE_HIGH)
            self._cancel_bindings(BindingType.CONTINUOUSLY_SCHEDULE_WHILE_HIGH)
            self._toggle_bindings(BindingType.TOGGLE_ON_FALLING_EDGE)

    def _read_signal(self) -> _Signal:
        return _Signal.HIGH if self._condition() else _Signal.LOW

    def _clear_stale_bindings(self) -> None:
        for binding_type, bindings in list(self._bindings.items()):
            still_active = []
            for binding in bindings:
                if binding.scope.active():
                    still_active.append(binding)
                    continue
                self._scheduler.cancel(binding.command)
            self._bindings[binding_type] = still_active

    def _schedule_bindings(self, binding_type: BindingType) -> None:
        for binding in self._bindings.get(binding_type, []):
            # Schedules using the binding's own scope, not a freshly
            # computed narrowest scope - the binding should keep governing
            # the same lifetime it was created with.
            self._scheduler._schedule_binding(binding)

    def _cancel_bindings(self, binding_type: BindingType) -> None:
        for binding in self._bindings.get(binding_type, []):
            self._scheduler.cancel(binding.command)

    def _toggle_bindings(self, binding_type: BindingType) -> None:
        for binding in self._bindings.get(binding_type, []):
            command = binding.command
            if self._scheduler.is_scheduled_or_running(command):
                self._scheduler.cancel(command)
            else:
                self._scheduler._schedule_binding(binding)

    # -- Scope/lifecycle ---------------------------------------------------

    def is_scope_active(self) -> bool:
        """Checks if the creation scope is currently active. Used by the scheduler."""
        return self._creation_scope.active()

    def unbind(self) -> None:
        """
        Unbinds this trigger from the event loop and cancels all bound
        commands. Automatically called by the scheduler when this trigger's
        creation scope goes inactive.
        """
        for bindings in self._bindings.values():
            for binding in bindings:
                self._scheduler.cancel(binding.command)
        self._bindings.clear()
        self._loop.unbind(self._poll)
        self._bound = False

    def add_binding(
        self, scope: BindingScope, binding_type: BindingType, command: Command
    ) -> None:
        """Adds a binding with an explicit scope, rather than the narrowest currently-active one. Mainly useful for tests."""
        self._bindings[binding_type].append(Binding(scope, binding_type, command))

        if not self._bound:
            self._loop.bind(self._poll)
            self._bound = True

    def _add_binding(self, binding_type: BindingType, command: Command) -> None:
        scope = create_narrowest_scope(self._scheduler)
        self.add_binding(scope, binding_type, command)

    @property
    def cached_signal(self) -> _Signal | None:
        """The signal as of the most recent poll(). For testing."""
        return self._cached_signal

    @property
    def previous_signal(self) -> _Signal | None:
        """The signal as of the poll() before the most recent one. For testing."""
        return self._previous_signal
