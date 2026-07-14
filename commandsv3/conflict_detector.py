# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""Finds pairs of commands that require the same mechanism and therefore can't run at the same time."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .command import Command
    from .mechanism import Mechanism

__all__ = ["Conflict", "find_all_conflicts", "throw_if_conflicts"]


@dataclass(frozen=True)
class Conflict:
    """A pair of commands that share at least one required mechanism."""

    a: Command
    b: Command
    shared_requirements: frozenset[Mechanism]

    def description(self) -> str:
        """A human-readable description naming both commands and the mechanisms they share."""
        shared = ", ".join(sorted(m.name for m in self.shared_requirements))
        return f"{self.a.name} and {self.b.name} both require {shared}"


def find_all_conflicts(commands: Iterable[Command]) -> list[Conflict]:
    """Finds every pair of commands in ``commands`` that share a required mechanism."""
    commands = list(commands)
    conflicts: list[Conflict] = []

    for i, command in enumerate(commands):
        for other in commands[i + 1 :]:
            if command is other:
                # Skip duplicate elements in the input; commands can't
                # conflict with themselves.
                continue

            if command.conflicts_with(other):
                shared = frozenset(command.requirements & other.requirements)
                conflicts.append(Conflict(command, other, shared))

    return conflicts


def throw_if_conflicts(commands: Iterable[Command]) -> None:
    """
    :raises ValueError: if any pair of commands in ``commands`` shares a
        required mechanism.
    """
    conflicts = find_all_conflicts(commands)
    if not conflicts:
        return

    message = "Commands running in parallel cannot share requirements: " + "; ".join(
        conflict.description() for conflict in conflicts
    )
    raise ValueError(message)
