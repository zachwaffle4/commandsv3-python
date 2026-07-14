# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Commands: the fundamental unit of work run by a ``Scheduler``.

There's no public constructor for ``Command`` - every command is built
through ``StagedCommandBuilder`` (or a shortcut like ``Mechanism.run()`` or
one of ``Command``'s static factory methods), which is split into stages so
that a name and a body are always set before a command can be created.
Skipping a required step is at least an ``AttributeError`` (the earlier
stage's methods aren't available on the next stage's object) rather than
silently building an incomplete command.

A command's body is a zero-argument ``async def`` function; calling it
produces the coroutine object the scheduler drives.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .coroutine import wait, wait_until

if TYPE_CHECKING:
    from .mechanism import Mechanism
    from .parallel_group import ParallelGroupBuilder
    from .sequential_group import SequentialGroupBuilder

__all__ = [
    "DEFAULT_PRIORITY",
    "LOWEST_PRIORITY",
    "HIGHEST_PRIORITY",
    "CommandBody",
    "Command",
    "StagedCommandBuilder",
    "NeedsExecutionBuilderStage",
    "NeedsNameBuilderStage",
]

# Priority is serialized as a 32-bit signed integer in scheduler telemetry,
# so these are bounded rather than using unbounded Python ints or +/-inf.
DEFAULT_PRIORITY = 0
LOWEST_PRIORITY = -(2**31)
HIGHEST_PRIORITY = 2**31 - 1

#: A command's body: a zero-argument callable that returns an awaitable.
#: Calling it starts a fresh run of the command; the scheduler drives the
#: returned coroutine one tick at a time.
CommandBody = Callable[[], Awaitable[None]]


def _no_op() -> None:
    pass


@dataclass(frozen=True, eq=False)
class Command:
    """
    Performs some task, optionally using one or more mechanisms.

    Commands require zero or more mechanisms. A running command has
    exclusive ownership of all of its required mechanisms: if another
    command with an equal or higher ``priority`` is scheduled that requires
    one of the same mechanisms, it interrupts and cancels the running one.

    Two ``Command`` instances are equal only if they're the same object -
    building the same configuration twice produces two distinct commands.

    :ivar name: the command's display name, used in logs and telemetry.
    :ivar requirements: the mechanisms this command requires exclusive
        ownership of while running.
    :ivar body: the command's implementation.
    :ivar priority: used to decide which of two conflicting commands wins;
        higher values win. Defaults to ``DEFAULT_PRIORITY``.
    :ivar on_cancel: called when the command is canceled before completing
        naturally. Should do simple, one-shot cleanup rather than looping
        logic.
    """

    name: str
    requirements: frozenset[Mechanism]
    body: CommandBody
    priority: int = DEFAULT_PRIORITY
    on_cancel: Callable[[], None] = field(default=_no_op)

    def requires(self, mechanism: Mechanism) -> bool:
        """Whether this command requires ``mechanism``."""
        return mechanism in self.requirements

    def conflicts_with(self, other: Command) -> bool:
        """Whether this command and ``other`` require at least one mechanism in common."""
        return not self.requirements.isdisjoint(other.requirements)

    def is_lower_priority_than(self, other: Command) -> bool:
        """Whether this command's priority is lower than ``other``'s."""
        return self.priority < other.priority

    def __repr__(self) -> str:
        return self.name

    @staticmethod
    def no_requirements(body: CommandBody) -> NeedsNameBuilderStage:
        """Starts building a command that doesn't require any mechanisms."""
        return StagedCommandBuilder().no_requirements().executing(body)

    @staticmethod
    def requiring(
        requirement: Mechanism, *rest: Mechanism
    ) -> NeedsExecutionBuilderStage:
        """Starts building a command that requires one or more mechanisms."""
        return StagedCommandBuilder().requiring(requirement, *rest)

    @staticmethod
    def wait_until(condition: Callable[[], bool]) -> NeedsNameBuilderStage:
        """Starts building a command that simply waits until ``condition`` is true."""
        return Command.no_requirements(lambda: wait_until(condition))

    @staticmethod
    def wait_for(seconds) -> NeedsNameBuilderStage:
        """Starts building a command that simply waits for the given duration."""
        return Command.no_requirements(lambda: wait(seconds))

    @staticmethod
    def parallel(*commands: Command) -> ParallelGroupBuilder:
        """Starts building a group that completes once every one of ``commands`` has completed."""
        from .parallel_group import ParallelGroupBuilder

        return ParallelGroupBuilder().requiring(*commands)

    @staticmethod
    def race(*commands: Command) -> ParallelGroupBuilder:
        """Starts building a group that completes once any one of ``commands`` completes, canceling the rest."""
        from .parallel_group import ParallelGroupBuilder

        return ParallelGroupBuilder().optional(*commands)

    @staticmethod
    def sequence(*commands: Command) -> SequentialGroupBuilder:
        """Starts building a sequence that runs ``commands`` one after another, in order."""
        from .sequential_group import SequentialGroupBuilder

        return SequentialGroupBuilder().and_then(*commands)

    def until(self, end_condition: Callable[[], bool]) -> ParallelGroupBuilder:
        """
        Starts building a group that runs this command and ends it early if
        ``end_condition`` becomes true before it finishes on its own.
        """
        from .parallel_group import ParallelGroupBuilder

        return ParallelGroupBuilder().optional(
            self, Command.wait_until(end_condition).named("Until Condition")
        )

    def and_then(self, next_command: Command) -> SequentialGroupBuilder:
        """Starts building a sequence that runs this command, then ``next_command``."""
        from .sequential_group import SequentialGroupBuilder

        return SequentialGroupBuilder().and_then(self).and_then(next_command)

    def along_with(self, *parallel: Command) -> ParallelGroupBuilder:
        """Starts building a group that runs this command alongside ``parallel``, completing once all have finished."""
        from .parallel_group import ParallelGroupBuilder

        return ParallelGroupBuilder().requiring(self).requiring(*parallel)

    def race_with(self, *parallel: Command) -> ParallelGroupBuilder:
        """Starts building a group that runs this command alongside ``parallel``, completing once any one finishes."""
        from .parallel_group import ParallelGroupBuilder

        return ParallelGroupBuilder().optional(self).optional(*parallel)

    def with_timeout(self, seconds) -> Command:
        """Returns a command that runs this one, canceling it if it's still running after ``seconds`` have elapsed."""
        timeout_command = Command.wait_for(seconds).named(f"Timeout: {seconds}s")
        return Command.race(self, timeout_command).named(
            f"{self.name} [{seconds}s timeout]"
        )


class _BuilderState:
    __slots__ = (
        "requirements",
        "body",
        "on_cancel",
        "priority",
        "end_condition",
        "built",
    )

    def __init__(self) -> None:
        self.requirements: set[Mechanism] = set()
        self.body: CommandBody | None = None
        self.on_cancel: Callable[[], None] = _no_op
        self.priority: int = DEFAULT_PRIORITY
        self.end_condition: Callable[[], bool] | None = None
        self.built: Command | None = None


def _throw_if_already_built(state: _BuilderState) -> None:
    if state.built is not None:
        raise RuntimeError("Command builders cannot be reused")


class NeedsExecutionBuilderStage:
    """A command builder stage where requirements can be set and a body is still needed."""

    def __init__(self, state: _BuilderState) -> None:
        self._state = state

    def requiring(
        self, requirement: Mechanism, *rest: Mechanism
    ) -> NeedsExecutionBuilderStage:
        """Adds one or more required mechanisms."""
        _throw_if_already_built(self._state)
        self._state.requirements.add(requirement)
        self._state.requirements.update(rest)
        return self

    def executing(self, body: CommandBody) -> NeedsNameBuilderStage:
        """Sets the command's body, advancing to the final builder stage."""
        _throw_if_already_built(self._state)
        self._state.body = body
        return NeedsNameBuilderStage(self._state)


class NeedsNameBuilderStage:
    """
    The final command builder stage: requirements and a body are set, and
    only a name is still needed before the command can be created.
    """

    def __init__(self, state: _BuilderState) -> None:
        self._state = state

    def when_canceled(self, on_cancel: Callable[[], None]) -> NeedsNameBuilderStage:
        """Sets a callback to run if the command is canceled before completing naturally."""
        _throw_if_already_built(self._state)
        self._state.on_cancel = on_cancel
        return self

    def with_priority(self, priority: int) -> NeedsNameBuilderStage:
        """Sets the command's priority."""
        _throw_if_already_built(self._state)
        self._state.priority = priority
        return self

    def until(self, end_condition: Callable[[], bool]) -> NeedsNameBuilderStage:
        """
        Sets an early-exit condition: if ``end_condition`` becomes true
        before the command finishes on its own, it's canceled. Calling this
        more than once replaces any previously-set condition.
        """
        _throw_if_already_built(self._state)
        self._state.end_condition = end_condition
        return self

    def named(self, name: str) -> Command:
        """Creates the command, giving it the specified name. The builder can't be reused afterward."""
        _throw_if_already_built(self._state)
        state = self._state

        command = Command(
            name=name,
            requirements=frozenset(state.requirements),
            body=state.body,
            priority=state.priority,
            on_cancel=state.on_cancel,
        )

        if state.end_condition is None:
            state.built = command
            return command

        # A custom end condition can't be injected into the command's body
        # directly, so it's realized as a race between the command and a
        # command that waits for the end condition.
        from .parallel_group import ParallelGroupBuilder

        built = (
            ParallelGroupBuilder()
            .requiring(command)
            .until(state.end_condition)
            .named(name)
        )
        state.built = built
        return built


class StagedCommandBuilder:
    """
    Builds a ``Command`` in stages: requirements, then a body, then optional
    configuration (priority, cancellation hook, end condition) followed by a
    name. Prefer a factory method like ``Mechanism.run()`` or
    ``Command.requiring()``/``Command.no_requirements()`` over constructing
    this directly.
    """

    def __init__(self) -> None:
        self._state = _BuilderState()

    def no_requirements(self) -> NeedsExecutionBuilderStage:
        """Marks the command as requiring no mechanisms."""
        _throw_if_already_built(self._state)
        return NeedsExecutionBuilderStage(self._state)

    def requiring(
        self, requirement: Mechanism, *rest: Mechanism
    ) -> NeedsExecutionBuilderStage:
        """Marks the command as requiring one or more mechanisms."""
        _throw_if_already_built(self._state)
        self._state.requirements.add(requirement)
        self._state.requirements.update(rest)
        return NeedsExecutionBuilderStage(self._state)

    def requiring_all(
        self, requirements: Iterable[Mechanism]
    ) -> NeedsExecutionBuilderStage:
        """Marks the command as requiring every mechanism in ``requirements``, which may be empty."""
        _throw_if_already_built(self._state)
        self._state.requirements.update(requirements)
        return NeedsExecutionBuilderStage(self._state)
