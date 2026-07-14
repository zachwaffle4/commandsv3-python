# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""Builds a command that runs several other commands one after another."""

from __future__ import annotations

from collections.abc import Callable

from .command import DEFAULT_PRIORITY, Command, StagedCommandBuilder
from .coroutine import await_

__all__ = ["SequentialGroupBuilder"]


def _build_sequential_group(name: str, commands: list[Command]) -> Command:
    requirements = frozenset().union(*(c.requirements for c in commands))
    priority = max((c.priority for c in commands), default=DEFAULT_PRIORITY)

    async def body() -> None:
        for command in commands:
            await await_(command)

    return (
        StagedCommandBuilder()
        .requiring_all(requirements)
        .executing(body)
        .with_priority(priority)
        .named(name)
    )


class SequentialGroupBuilder:
    """
    Builds a command that runs a series of steps one after another, each
    only starting once its predecessor has completed. Completes once the
    last step finishes.
    """

    def __init__(self) -> None:
        self._steps: list[Command] = []
        self._end_condition: Callable[[], bool] | None = None

    def and_then(self, *next_commands: Command) -> SequentialGroupBuilder:
        """Adds one or more commands to the sequence, in the order given."""
        self._steps.extend(next_commands)
        return self

    def until(self, end_condition: Callable[[], bool]) -> SequentialGroupBuilder:
        """Sets an early-exit end condition; the latest call wins if called more than once."""
        self._end_condition = end_condition
        return self

    def named(self, name: str) -> Command:
        """Creates the sequence command, giving it the specified name."""
        seq = _build_sequential_group(name, list(self._steps))
        if self._end_condition is None:
            return seq

        from .parallel_group import ParallelGroupBuilder

        return (
            ParallelGroupBuilder()
            .optional(
                seq, Command.wait_until(self._end_condition).named("Until Condition")
            )
            .named(name)
        )

    def with_automatic_name(self) -> Command:
        """Creates the sequence command with a name derived from its steps' names."""
        return self.named(" -> ".join(c.name for c in self._steps))
