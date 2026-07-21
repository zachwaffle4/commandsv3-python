# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""Builds a command that runs several other commands at the same time."""

from __future__ import annotations

from collections.abc import Callable

from .command import DEFAULT_PRIORITY, Command, StagedCommandBuilder
from .conflict_detector import throw_if_conflicts
from .coroutine import all_of, any_of, fork

__all__ = ["ParallelGroupBuilder"]


def _build_parallel_group(
    name: str, required_commands: list[Command], optional_commands: list[Command]
) -> Command:
    # De-duplicated by identity, required first then optional.
    all_commands = list(dict.fromkeys([*required_commands, *optional_commands]))
    throw_if_conflicts(all_commands)

    requirements = frozenset().union(*(c.requirements for c in all_commands))
    priority = max((c.priority for c in all_commands), default=DEFAULT_PRIORITY)

    async def body() -> None:
        fork(*optional_commands)

        if not required_commands:
            # No required commands - just wait for the first optional command
            # to finish. Note: fork() and any_of() both touch the same
            # optional_commands collection. A member that completes with
            # zero yields would already be "done" by the time any_of()
            # re-schedules it, causing it to run a second time - avoid using
            # a zero-yield command as a group member (see test_parallel_group.py).
            await any_of(optional_commands)
        else:
            # Wait for every required command to finish.
            await all_of(required_commands)

        # The scheduler cancels any optional child commands still running
        # once this returns.

    return (
        StagedCommandBuilder()
        .requiring_all(requirements)
        .executing(body)
        .with_priority(priority)
        .named(name)
    )


class ParallelGroupBuilder:
    """
    Builds a command that runs a group of commands at the same time.
    Completes once every *required* command has completed; if none are
    required, completes once any *optional* command completes and cancels
    the rest.
    """

    def __init__(self) -> None:
        self._optional_commands: dict[Command, None] = {}
        self._required_commands: dict[Command, None] = {}
        self._end_condition: Callable[[], bool] | None = None

    def optional(self, *commands: Command) -> ParallelGroupBuilder:
        """Adds optional commands: not required to complete, canceled once the group is done."""
        for command in commands:
            self._optional_commands[command] = None
        return self

    def requiring(self, *commands: Command) -> ParallelGroupBuilder:
        """Adds required commands: all must complete for the group to exit."""
        for command in commands:
            self._required_commands[command] = None
        return self

    def along_with(self, command: Command) -> ParallelGroupBuilder:
        """Adds a required command. Exists mainly to chain ``.along_with()`` calls fluently."""
        return self.requiring(command)

    def until(self, condition: Callable[[], bool]) -> ParallelGroupBuilder:
        """Sets an early-exit end condition; the latest call wins if called more than once."""
        self._end_condition = condition
        return self

    def named(self, name: str) -> Command:
        """Creates the group. Requires everything its commands require; priority is the max of theirs."""
        group = _build_parallel_group(
            name, list(self._required_commands), list(self._optional_commands)
        )
        if self._end_condition is None:
            return group

        # Wrap in a race against the end condition.
        return (
            ParallelGroupBuilder()
            .optional(
                group, Command.wait_until(self._end_condition).named("Until Condition")
            )
            .named(name)
        )

    def with_automatic_name(self) -> Command:
        """Creates the group with a name derived from its commands' names."""
        required = "(" + " & ".join(c.name for c in self._required_commands) + ")"
        optional = "(" + " | ".join(c.name for c in self._optional_commands) + ")"

        if not self._required_commands:
            return self.named(optional)
        elif not self._optional_commands:
            return self.named(required)
        else:
            return self.named(f"[{required} * {optional}]")
