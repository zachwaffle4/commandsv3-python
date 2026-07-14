# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
The ``Scheduler`` manages the lifecycle of every command: scheduling,
running, canceling, resolving conflicts between commands that require the
same mechanism, and driving default commands, triggers, and the event loop.

Not yet implemented here: sideloaded periodic callbacks, protobuf
telemetry, and the ``SchedulerEvent`` listener mechanism.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Any

import wpilib

from . import (
    execution_context as ec,
    BindingType,
    ForCommand,
    ForOpMode,
    create_narrowest_scope,
)
from .binding import Binding
from .event_loop import EventLoop
from .exceptions import CommandCancelled

if TYPE_CHECKING:
    from .command import Command
    from .mechanism import Mechanism
    from .trigger import Trigger

__all__ = ["ScheduleResult", "Scheduler"]


def _require_valid_default_command(
    mechanism: Mechanism, default_command: Command
) -> None:
    if not default_command.requires(mechanism):
        raise ValueError("A mechanism's default command must require that mechanism")
    if len(default_command.requirements) > 1:
        raise ValueError(
            "A mechanism's default command cannot require other mechanisms"
        )


class ScheduleResult(enum.Enum):
    """The outcome of a ``Scheduler.schedule()`` call."""

    #: The command was successfully scheduled and added to the queue.
    SUCCESS = enum.auto()

    #: The command is already scheduled or running.
    ALREADY_RUNNING = enum.auto()

    #: The command is a lower priority than, and conflicts with, an
    #: already-scheduled or already-running command.
    LOWER_PRIORITY_THAN_RUNNING_COMMAND = enum.auto()


class Scheduler:
    """
    Runs commands, resolving conflicts by priority when two commands
    require the same mechanism. Call ``run()`` periodically (e.g. from a
    robot's periodic loop) to advance every scheduled and running command,
    poll triggers, and process default commands.

    Use ``Scheduler.get_default()`` for the shared instance most code should
    use; use ``create_independent_scheduler()`` to create an isolated
    instance, useful for tests.
    """

    _default_scheduler: Scheduler | None = None

    def __init__(self) -> None:
        # Ordered narrowest-last: the last entry for a mechanism is the one
        # actually in effect.
        self._default_command_bindings: dict[Mechanism, list[Binding]] = {}
        # All bindings created via schedule(); checked each run() for scopes
        # that have gone inactive.
        self._active_bindings: list[Binding] = []
        # Both keyed by Command (a command can only be queued/running once,
        # enforced by is_scheduled_or_running()), preserving insertion order.
        self._queued_to_run: dict[Command, CommandState] = {}
        self._running_commands: dict[Command, CommandState] = {}
        self._last_run_time_ms: float = -1.0
        self._event_loop = EventLoop()
        self._bound_triggers: list[Trigger] = []

    @staticmethod
    def get_default() -> Scheduler:
        """The shared default scheduler instance, created on first use."""
        if Scheduler._default_scheduler is None:
            Scheduler._default_scheduler = Scheduler()
        return Scheduler._default_scheduler

    @staticmethod
    def create_independent_scheduler() -> Scheduler:
        """Creates a new scheduler instance independent of the default one. Useful for tests."""
        return Scheduler()

    # -- Default commands -----------------------------------------------

    def set_default_command(
        self, mechanism: Mechanism, default_command: Command
    ) -> None:
        """
        Sets the command to run on ``mechanism`` whenever no other command
        is using it. ``default_command`` must require ``mechanism`` and
        nothing else.

        If called from within a running command or opmode, the default
        command is scoped to it: it's replaced by whatever wider-scoped
        default command was previously set once that command or opmode
        exits.

        :raises ValueError: if ``default_command`` doesn't require
            ``mechanism``, or requires any other mechanism too.
        """
        _require_valid_default_command(mechanism, default_command)

        current_command = ec.current_command()
        scope = create_narrowest_scope(self)
        self._add_default_command_binding(
            mechanism, default_command, current_command, scope
        )

    def set_default_command_for_opmode(
        self, opmode_name: str, mechanism: Mechanism, default_command: Command
    ) -> None:
        """
        Like ``set_default_command()``, but explicitly scoped to the named
        opmode rather than the narrowest currently-active scope - useful for
        configuring an opmode's defaults before it's ever been selected.
        """
        _require_valid_default_command(mechanism, default_command)

        current_command = ec.current_command()
        scope = ForOpMode(opmode_name)
        self._add_default_command_binding(
            mechanism, default_command, current_command, scope
        )

    def _add_default_command_binding(
        self,
        mechanism: Mechanism,
        default_command: Command,
        current_command: Command | None,
        scope,
    ) -> None:
        binding = Binding(
            scope, BindingType.CONTINUOUSLY_SCHEDULE_WHILE_HIGH, default_command
        )
        current_default = self.get_default_command_for(mechanism)

        self._default_command_bindings.setdefault(mechanism, []).append(binding)

        if current_command is not None and current_command is not current_default:
            # Keep this mechanism in sync with the rest of the scheduler
            # right away instead of waiting for the next run() to pick up
            # the new default command.
            self._process_default_command(mechanism)

    def remove_default_command(self, opmode_name: str, mechanism: Mechanism) -> None:
        """Removes the default command that was scoped to ``opmode_name`` for ``mechanism``."""
        bindings = self._default_command_bindings.get(mechanism)
        if not bindings:
            return

        removed = False
        remaining = []
        for binding in bindings:
            if (
                isinstance(binding.scope, ForOpMode)
                and binding.scope.opmode_name == opmode_name
            ):
                if ec.current_command() is binding.command:
                    # Can't cancel while mounted; leave the rest alone too.
                    return
                self.cancel(binding.command)
                removed = True
                continue
            remaining.append(binding)

        self._default_command_bindings[mechanism] = remaining

        if removed:
            self._process_default_command(mechanism)

    def get_default_command_for(self, mechanism: Mechanism) -> Command | None:
        """The command currently configured to run on ``mechanism`` when nothing else is, or ``None``."""
        bindings = self._default_command_bindings.get(mechanism)
        if not bindings:
            return None
        return bindings[-1].command

    def _schedule_default_commands(self) -> None:
        for mechanism in list(self._default_command_bindings.keys()):
            self._process_default_command(mechanism)

    def _process_default_command(self, mechanism: Mechanism) -> None:
        bindings = self._default_command_bindings.get(mechanism)
        if not bindings:
            return

        # Cancel (and, for transient ForCommand bindings, drop) any bindings
        # whose scope has gone inactive. ForOpMode bindings are persistent -
        # only canceled, not removed - so they reactivate when their opmode
        # is selected again.
        remaining = []
        for binding in bindings:
            if not binding.scope.active():
                self.cancel(binding.command)
                if isinstance(binding.scope, ForCommand):
                    continue
            remaining.append(binding)
        self._default_command_bindings[mechanism] = remaining
        bindings = remaining

        active_bindings = [b for b in bindings if b.scope.active()]
        if not active_bindings:
            return

        # Cancel every default command except the narrowest-scoped one (the
        # last binding in the list).
        for binding in active_bindings[:-1]:
            self.cancel(binding.command)

        for command in self._running_commands:
            if command.requires(mechanism):
                return
        for state in self._queued_to_run.values():
            if state.command.requires(mechanism):
                return

        self.schedule(active_bindings[-1].command)

    # -- Scheduling --------------------------------------------------------

    def schedule(self, command: Command) -> ScheduleResult:
        """
        Schedules ``command`` to run. If scheduled from within another
        command, ``command`` becomes a child of it and starts running
        immediately rather than waiting for the next ``run()``; its
        lifetime is tied to its parent's.

        Has no effect (returns without scheduling) if the command is
        already scheduled or running, or if it requires a mechanism already
        in use by a higher-priority command.
        """
        scope = create_narrowest_scope(self)
        binding = Binding(scope, BindingType.IMMEDIATE, command)
        return self._schedule_binding(binding)

    def _schedule_binding(self, binding: Binding) -> ScheduleResult:
        command = binding.command

        if self.is_scheduled_or_running(command):
            return ScheduleResult.ALREADY_RUNNING

        if self._lower_priority_than_conflicting_commands(command):
            return ScheduleResult.LOWER_PRIORITY_THAN_RUNNING_COMMAND

        for scheduled_state in self._queued_to_run.values():
            if not command.conflicts_with(scheduled_state.command):
                continue
            if command.is_lower_priority_than(scheduled_state.command):
                return ScheduleResult.LOWER_PRIORITY_THAN_RUNNING_COMMAND

        # Track this binding so we can disable it when it's out of scope.
        self._active_bindings.append(binding)

        self._evict_conflicting_on_deck_commands(command)

        # If the binding is scoped to a particular command, that command is
        # the parent. Otherwise, whatever command is currently running (if
        # any) is the parent.
        parent_command = (
            binding.scope.command
            if isinstance(binding.scope, ForCommand)
            else ec.current_command()
        )
        state = CommandState(command, parent_command, command.body(), self, binding)

        if ec.current_state() is not None:
            # Scheduling a child command while running: start it immediately
            # rather than waiting for the next run(), so deeply nested
            # commands don't take many scheduler cycles to actually start.
            self._evict_conflicting_running_commands(state)
            self._running_commands[command] = state
            self._run_command(state)
        else:
            self._queued_to_run[command] = state

        return ScheduleResult.SUCCESS

    def _lower_priority_than_conflicting_commands(self, command: Command) -> bool:
        ancestors = set()
        state = ec.current_state()
        while state is not None:
            ancestors.add(state)
            state = (
                self._running_commands.get(state.parent)
                if state.parent is not None
                else None
            )

        for state in self._running_commands.values():
            if state in ancestors:
                continue
            if state.command.conflicts_with(command) and command.is_lower_priority_than(
                state.command
            ):
                return True

        return False

    def _evict_conflicting_on_deck_commands(self, command: Command) -> None:
        for scheduled_command, scheduled_state in list(self._queued_to_run.items()):
            if scheduled_state.command.conflicts_with(command):
                del self._queued_to_run[scheduled_command]
                self._discard_unstarted_coroutine(scheduled_state)

    def _evict_conflicting_running_commands(self, incoming_state: CommandState) -> None:
        conflicting_roots = set()

        for state in list(self._running_commands.values()):
            if not incoming_state.command.conflicts_with(state.command):
                continue
            if self._is_ancestor_of(state.command, incoming_state):
                continue

            root = state
            while root.parent is not None and root.parent is not incoming_state.parent:
                next_root = self._running_commands.get(root.parent)
                if next_root is None:
                    break
                root = next_root
            conflicting_roots.add(root)

        for conflicting_state in conflicting_roots:
            self.cancel(conflicting_state.command)

    def _is_ancestor_of(self, ancestor: Command, state: CommandState) -> bool:
        if state.parent is None:
            return False
        if ancestor not in self._running_commands:
            return False
        if state.parent is ancestor:
            return True

        parent_state = self._running_commands.get(state.parent)
        if parent_state is None:
            return False
        return self._is_ancestor_of(ancestor, parent_state)

    # -- Cancellation --------------------------------------------------------

    def cancel(self, command: Command) -> None:
        """
        Cancels ``command`` immediately, along with any commands it
        scheduled. Has no effect if the command isn't currently scheduled
        or running.

        Cancellation runs any pending ``try/finally`` cleanup in the
        command's body before its ``on_cancel`` hook, so cleanup can go in
        either place.

        :raises ValueError: if ``command`` is the command currently
            executing - a command can't cancel itself while running.
        """
        if command is ec.current_command():
            raise ValueError(
                f"Command `{command.name}` is mounted and cannot be canceled"
            )

        state = self._running_commands.pop(command, None)
        was_running = state is not None

        queued_state = self._queued_to_run.pop(command, None)
        if queued_state is not None:
            # Never started running, so there's nothing to clean up - just
            # close the unstarted coroutine object so Python doesn't warn
            # about it being garbage collected without ever running.
            self._discard_unstarted_coroutine(queued_state)

        if was_running:
            self._cancel_coroutine(state)
            command.on_cancel()

        self._remove_orphaned_children(command)

    @staticmethod
    def _cancel_coroutine(state: CommandState) -> None:
        try:
            state.coroutine.throw(CommandCancelled)
        except (CommandCancelled, StopIteration):
            pass

    @staticmethod
    def _discard_unstarted_coroutine(state: CommandState) -> None:
        # Not a cancellation - the coroutine never started running, so
        # there's nothing to clean up. Just close it so Python doesn't warn
        # about a coroutine object being garbage collected unawaited.
        state.coroutine.close()

    def _remove_orphaned_children(self, parent: Command) -> None:
        children = [
            command
            for command, state in self._running_commands.items()
            if state.parent is parent
        ]
        for child in children:
            self.cancel(child)

    def cancel_all(self) -> None:
        """
        Cancels every currently scheduled and running command. Any default
        commands will be scheduled again on the next ``run()``, unless
        superseded by a higher-priority command scheduled first.
        """
        for state in self._queued_to_run.values():
            self._discard_unstarted_coroutine(state)
        self._queued_to_run.clear()

        running = list(self._running_commands.items())
        self._running_commands.clear()
        for command, state in running:
            self._cancel_coroutine(state)
            command.on_cancel()

    # -- Run loop --------------------------------------------------------

    def run(self) -> None:
        """
        Advances the scheduler by one tick. In order: cancels commands and
        unbinds triggers whose scope has gone inactive, polls the event
        loop (running triggers and scheduling/canceling bound commands),
        schedules default commands for idle mechanisms, promotes queued
        commands to running, then runs every running command until it
        yields or completes.

        Call this periodically, e.g. from a robot's periodic loop.
        """
        start = wpilib.RobotController.get_time()

        self._cancel_stale_bindings()
        self._unbind_stale_triggers()
        self._event_loop.poll()
        self._schedule_default_commands()
        self._promote_scheduled_commands()
        self._run_commands()

        end = wpilib.RobotController.get_time()
        self._last_run_time_ms = (end - start) / 1000.0

    def _cancel_stale_bindings(self) -> None:
        still_active = []
        for binding in self._active_bindings:
            if binding.scope.active():
                still_active.append(binding)
                continue
            self.cancel(binding.command)
        self._active_bindings = still_active

    def _unbind_stale_triggers(self) -> None:
        still_bound = []
        for trigger in self._bound_triggers:
            if trigger.is_scope_active():
                still_bound.append(trigger)
                continue
            trigger.unbind()
        self._bound_triggers = still_bound

    def get_default_event_loop(self) -> EventLoop:
        """The event loop this scheduler polls on every ``run()`` to update and fire triggers."""
        return self._event_loop

    def _add_bound_trigger(self, trigger: Trigger) -> None:
        # Called by Trigger's constructor. Unbound automatically once its
        # creation scope goes inactive.
        self._bound_triggers.append(trigger)

    def _promote_scheduled_commands(self) -> None:
        for state in list(self._queued_to_run.values()):
            self._evict_conflicting_running_commands(state)

        for command, state in self._queued_to_run.items():
            self._running_commands[command] = state

        self._queued_to_run.clear()

    def _run_commands(self) -> None:
        # Run in reverse so a parent command can resume in the same tick a
        # child command it's awaiting completes in, instead of waiting an
        # extra tick per level of nesting.
        for state in list(reversed(list(self._running_commands.values()))):
            self._run_command(state)

    def _run_command(self, state: CommandState) -> None:
        command = state.command
        coroutine = state.coroutine

        if command not in self._running_commands:
            # Probably canceled by an owning composition; do not run.
            return

        start = wpilib.RobotController.get_time()
        done = False
        error: BaseException | None = None
        with ec.mounted(state):
            try:
                coroutine.send(None)
            except StopIteration:
                done = True
            except CommandCancelled:
                done = True
            except Exception as e:  # noqa: BLE001 - deliberately broad, see below
                error = e
        end = wpilib.RobotController.get_time()
        state.set_last_runtime_ms((end - start) / 1000.0)

        if error is not None:
            self._handle_command_exception(state, error)
            return

        if done:
            self._running_commands.pop(command, None)
            self._remove_orphaned_children(command)

    def _handle_command_exception(
        self, state: CommandState, error: BaseException
    ) -> None:
        command = state.command

        # Find the root ancestor before removing the failed command from the
        # running set, since get_parent_of() reads from that set.
        root: Command | None = command
        while self.get_parent_of(root) is not None:
            root = self.get_parent_of(root)

        self._running_commands.pop(command, None)
        self._remove_orphaned_children(command)

        if root is not None and root is not command:
            self.cancel(root)

        raise error

    # -- Queries --------------------------------------------------------

    def is_running(self, command: Command) -> bool:
        """Whether ``command`` is currently running."""
        return command in self._running_commands

    def is_scheduled(self, command: Command) -> bool:
        """Whether ``command`` is scheduled to run but hasn't started yet."""
        return command in self._queued_to_run

    def is_scheduled_or_running(self, command: Command) -> bool:
        """Whether ``command`` is either scheduled or already running."""
        return self.is_scheduled(command) or self.is_running(command)

    def get_running_commands(self) -> list[Command]:
        """Every currently running command, in the order they were scheduled."""
        return list(self._running_commands.keys())

    def get_running_commands_for(self, mechanism: Mechanism) -> list[Command]:
        """Every currently running command that requires ``mechanism``."""
        return [
            command for command in self._running_commands if command.requires(mechanism)
        ]

    def current_command(self) -> Command | None:
        """The command currently being run, or ``None`` if none is."""
        return ec.current_command()

    def get_parent_of(self, command: Command) -> Command | None:
        """The command that scheduled ``command``, or ``None`` if it wasn't scheduled by another command."""
        state = self._running_commands.get(command)
        return state.parent if state is not None else None

    def last_command_runtime_ms(self, command: Command) -> float:
        """How long ``command`` took to run its last tick, in milliseconds, or ``-1`` if it isn't running."""
        state = self._running_commands.get(command)
        return state.last_runtime_ms if state is not None else -1.0

    def total_runtime_ms(self, command: Command) -> float:
        """How long ``command`` has run in total since it was last scheduled, or ``-1`` if it isn't running."""
        state = self._running_commands.get(command)
        return state.total_runtime_ms if state is not None else -1.0

    def run_id(self, command: Command) -> int:
        """A unique, monotonically increasing ID for the current run of ``command``, or ``0`` if it isn't scheduled or running."""
        state = self._running_commands.get(command)
        if state is not None:
            return state.id
        state = self._queued_to_run.get(command)
        if state is not None:
            return state.id
        return 0

    def last_runtime_ms(self) -> float:
        """How long the most recent call to ``run()`` took, in milliseconds."""
        return self._last_run_time_ms


class CommandState:
    """
    Tracks a single running (or scheduled) command: the command itself, the
    command that scheduled it (if any), the coroutine backing its
    execution, the scheduler running it, the binding that caused it to be
    scheduled, and timing data.
    """

    # A fresh CommandState is allocated on every schedule() call - every
    # button press, every default-command cycle, every forked child - so
    # this is the actual hot-path allocation in the framework. __slots__
    # cuts per-instance memory and attribute-access overhead.
    __slots__ = (
        "command",
        "parent",
        "coroutine",
        "scheduler",
        "binding",
        "last_runtime_ms",
        "total_runtime_ms",
        "id",
    )

    _last_id = 0

    def __init__(
        self,
        command: Command,
        parent: Command | None,
        coroutine: Any,
        scheduler: Scheduler,
        binding: Binding,
    ) -> None:
        self.command = command
        self.parent = parent
        self.coroutine = coroutine
        self.scheduler = scheduler
        self.binding = binding
        self.last_runtime_ms: float = -1.0
        self.total_runtime_ms: float = 0.0

        # Not thread-safe - fine, since the framework is single-threaded only.
        CommandState._last_id += 1
        self.id = CommandState._last_id

    def set_last_runtime_ms(self, last_runtime_ms: float) -> None:
        """Records how long the most recent tick took, adding it to the running total."""
        self.last_runtime_ms = last_runtime_ms
        self.total_runtime_ms += last_runtime_ms

    def __repr__(self) -> str:
        return (
            f"CommandState(command={self.command!r}, parent={self.parent!r}, "
            f"id={self.id})"
        )
