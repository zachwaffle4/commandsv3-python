# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import pytest

from commandsv3 import Command, Mechanism, find_all_conflicts, throw_if_conflicts


class DummyMechanism(Mechanism):
    pass


async def _noop_body() -> None:
    pass


def test_find_all_conflicts_detects_shared_requirement():
    m1 = DummyMechanism("m1")
    m2 = DummyMechanism("m2")

    a = Command.requiring(m1).executing(_noop_body).named("A")
    b = Command.requiring(m1, m2).executing(_noop_body).named("B")
    c = Command.no_requirements(_noop_body).named("C")

    conflicts = find_all_conflicts([a, b, c])

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert {conflict.a, conflict.b} == {a, b}
    assert conflict.shared_requirements == frozenset({m1})


def test_find_all_conflicts_reports_each_pair_once():
    m = DummyMechanism()
    a = Command.requiring(m).executing(_noop_body).named("A")
    b = Command.requiring(m).executing(_noop_body).named("B")
    c = Command.requiring(m).executing(_noop_body).named("C")

    conflicts = find_all_conflicts([a, b, c])

    assert len(conflicts) == 3


def test_find_all_conflicts_empty_when_no_shared_requirements():
    m1 = DummyMechanism("m1")
    m2 = DummyMechanism("m2")
    a = Command.requiring(m1).executing(_noop_body).named("A")
    b = Command.requiring(m2).executing(_noop_body).named("B")

    assert find_all_conflicts([a, b]) == []


def test_throw_if_conflicts_raises_value_error_with_description():
    m = DummyMechanism("Arm")
    a = Command.requiring(m).executing(_noop_body).named("A")
    b = Command.requiring(m).executing(_noop_body).named("B")

    with pytest.raises(ValueError, match="A and B both require Arm"):
        throw_if_conflicts([a, b])


def test_throw_if_conflicts_does_nothing_when_no_conflicts():
    m1 = DummyMechanism()
    m2 = DummyMechanism()
    a = Command.requiring(m1).executing(_noop_body).named("A")
    b = Command.requiring(m2).executing(_noop_body).named("B")

    throw_if_conflicts([a, b])  # should not raise
