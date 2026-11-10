# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import pytest

from commands3 import (
    Command,
    Conflict,
    Mechanism,
    find_all_conflicts,
    throw_if_conflicts,
)


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


def test_empty_input_has_no_conflicts():
    assert find_all_conflicts([]) == []


def test_single_input_has_no_conflicts():
    mech = DummyMechanism("Mech")
    command = Command.requiring(mech).executing(_noop_body).named("Command")

    assert find_all_conflicts([command]) == []


def test_command_does_not_conflict_with_itself():
    mech = DummyMechanism("Mech")
    command = Command.requiring(mech).executing(_noop_body).named("Command")

    assert find_all_conflicts([command, command]) == []


def test_detects_many_conflicts_in_order_with_a_full_error_message():
    mech1 = DummyMechanism("Mech 1")
    mech2 = DummyMechanism("Mech 2")

    command1 = Command.requiring(mech1, mech2).executing(_noop_body).named("Command1")
    command2 = Command.requiring(mech1).executing(_noop_body).named("Command2")
    command3 = Command.requiring(mech2).executing(_noop_body).named("Command3")
    command4 = Command.requiring(mech2, mech1).executing(_noop_body).named("Command4")
    all_commands = [command1, command2, command3, command4]

    conflicts = find_all_conflicts(all_commands)

    assert conflicts == [
        Conflict(command1, command2, frozenset({mech1})),
        Conflict(command1, command3, frozenset({mech2})),
        Conflict(command1, command4, frozenset({mech1, mech2})),
        Conflict(command2, command4, frozenset({mech1})),
        Conflict(command3, command4, frozenset({mech2})),
    ]

    with pytest.raises(ValueError) as raised:
        throw_if_conflicts(all_commands)

    assert str(raised.value) == (
        "Commands running in parallel cannot share requirements: "
        "Command1 and Command2 both require Mech 1; "
        "Command1 and Command3 both require Mech 2; "
        "Command1 and Command4 both require Mech 1, Mech 2; "
        "Command2 and Command4 both require Mech 1; "
        "Command3 and Command4 both require Mech 2"
    )
