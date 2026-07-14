# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import pytest
import wpilib.simulation as simulation

from commandsv3 import (
    Command,
    Mechanism,
    ParallelGroupBuilder,
    Scheduler,
    await_,
    yield_,
)


class DummyMechanism(Mechanism):
    pass


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


def _forever(mechanism, name):
    async def body():
        while True:
            await yield_()

    return Command.requiring(mechanism).executing(body).named(name)


def _one_shot(mechanism, name, ran):
    async def body():
        ran.append(name)

    return Command.requiring(mechanism).executing(body).named(name)


def test_requirements_are_the_union_of_all_commands(scheduler):
    m1, m2, m3 = DummyMechanism("m1"), DummyMechanism("m2"), DummyMechanism("m3")
    a = _forever(m1, "A")
    b = _forever(m2, "B")
    c = _forever(m3, "C")

    group = ParallelGroupBuilder().requiring(a).optional(b, c).named("Group")

    assert group.requirements == frozenset({m1, m2, m3})


def test_priority_is_the_max_of_all_commands(scheduler):
    m1, m2 = DummyMechanism("m1"), DummyMechanism("m2")

    async def body():
        while True:
            await yield_()

    a = Command.requiring(m1).executing(body).with_priority(1).named("A")
    b = Command.requiring(m2).executing(body).with_priority(5).named("B")

    group = ParallelGroupBuilder().requiring(a, b).named("Group")

    assert group.priority == 5


def test_conflicting_commands_in_the_group_raise(scheduler):
    m = DummyMechanism()
    a = _forever(m, "A")
    b = _forever(m, "B")

    with pytest.raises(ValueError):
        ParallelGroupBuilder().requiring(a, b).named("Group")


def test_group_waits_for_all_required_commands(scheduler):
    m1, m2, m3 = DummyMechanism("m1"), DummyMechanism("m2"), DummyMechanism("m3")
    ran = []
    a = _one_shot(m1, "A", ran)
    b = _one_shot(m2, "B", ran)

    group = ParallelGroupBuilder().requiring(a, b).named("Group")

    async def outer_body():
        await await_(group)

    outer = Command.requiring(m3).executing(outer_body).named("Outer")
    scheduler.schedule(outer)
    scheduler.run()

    assert set(ran) == {"A", "B"}
    assert not scheduler.is_running(outer)


def test_group_with_no_required_commands_waits_for_any_optional(scheduler):
    # Ports Java's ParallelGroupTest#race: members always yield at least once
    # before finishing. A member that completes with zero yields would
    # already be done by the time fork() and awaitAny() both touch the same
    # optional-commands collection - an edge case Java's own tests avoid too.
    m1, m2 = DummyMechanism("m1"), DummyMechanism("m2")
    ran = []

    async def fast_body():
        await yield_()
        ran.append("Fast")

    fast = Command.requiring(m1).executing(fast_body).named("Fast")
    slow = _forever(m2, "Slow")

    group = ParallelGroupBuilder().optional(fast, slow).named("Group")
    scheduler.schedule(group)
    scheduler.run()
    scheduler.run()

    assert ran == ["Fast"]
    assert not scheduler.is_running(group)
    assert not scheduler.is_scheduled_or_running(slow)


def test_optional_commands_are_canceled_once_required_ones_finish(scheduler):
    m1, m2 = DummyMechanism("m1"), DummyMechanism("m2")
    ran = []
    required = _one_shot(m1, "Required", ran)
    optional = _forever(m2, "Optional")

    group = ParallelGroupBuilder().requiring(required).optional(optional).named("Group")
    scheduler.schedule(group)
    scheduler.run()

    assert ran == ["Required"]
    assert not scheduler.is_running(group)
    assert not scheduler.is_scheduled_or_running(optional)


def test_with_automatic_name_for_required_and_optional():
    m1, m2 = DummyMechanism("m1"), DummyMechanism("m2")
    a = _forever(m1, "A")
    b = _forever(m2, "B")

    group = ParallelGroupBuilder().requiring(a).named("A")
    assert group.name == "A"

    pure_race = ParallelGroupBuilder().optional(a, b).with_automatic_name()
    assert pure_race.name == "(A | B)"

    pure_required = ParallelGroupBuilder().requiring(a, b).with_automatic_name()
    assert pure_required.name == "(A & B)"


def test_command_race_completes_when_first_command_finishes(scheduler):
    m1, m2 = DummyMechanism("m1"), DummyMechanism("m2")
    ran = []
    fast = _one_shot(m1, "Fast", ran)
    slow = _forever(m2, "Slow")

    race = Command.race(fast, slow).named("Race")
    scheduler.schedule(race)
    scheduler.run()

    assert not scheduler.is_running(race)
    assert not scheduler.is_scheduled_or_running(slow)


def test_command_along_with_and_race_with():
    m1, m2, m3 = DummyMechanism("m1"), DummyMechanism("m2"), DummyMechanism("m3")
    a = _forever(m1, "A")
    b = _forever(m2, "B")
    c = _forever(m3, "C")

    grouped = a.along_with(b, c).named("Grouped")
    assert grouped.requirements == frozenset({m1, m2, m3})

    raced = a.race_with(b).named("Raced")
    assert raced.requirements == frozenset({m1, m2})


def test_command_with_timeout_cancels_after_duration(scheduler):
    m = DummyMechanism()
    command = _forever(m, "Forever").with_timeout(1.0)

    simulation.pause_timing()
    try:
        scheduler.schedule(command)
        scheduler.run()
        assert scheduler.is_running(command)

        simulation.step_timing(1.1)
        scheduler.run()
        assert not scheduler.is_running(command)
    finally:
        simulation.resume_timing()
