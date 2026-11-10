# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import pytest

from commands3 import Command, Mechanism, Scheduler, SequentialGroupBuilder, yield_


class DummyMechanism(Mechanism):
    pass


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


def _step(mechanism, name, order, ticks=1):
    async def body():
        for _ in range(ticks):
            await yield_()
        order.append(name)

    return Command.requiring(mechanism).executing(body).named(name)


def test_requirements_are_the_union_of_all_steps():
    m1, m2 = DummyMechanism("m1"), DummyMechanism("m2")
    order = []
    a = _step(m1, "A", order)
    b = _step(m2, "B", order)

    seq = SequentialGroupBuilder().and_then(a).and_then(b).named("Sequence")

    assert seq.requirements == frozenset({m1, m2})


def test_priority_is_the_max_of_all_steps():
    m1, m2 = DummyMechanism("m1"), DummyMechanism("m2")

    async def noop():
        pass

    a = Command.requiring(m1).executing(noop).with_priority(2).named("A")
    b = Command.requiring(m2).executing(noop).with_priority(7).named("B")

    seq = SequentialGroupBuilder().and_then(a, b).named("Sequence")

    assert seq.priority == 7


def test_steps_run_in_order(scheduler):
    m1, m2, m3 = DummyMechanism("m1"), DummyMechanism("m2"), DummyMechanism("m3")
    order = []
    a = _step(m1, "A", order)
    b = _step(m2, "B", order)
    c = _step(m3, "C", order)

    seq = SequentialGroupBuilder().and_then(a, b, c).named("Sequence")
    scheduler.schedule(seq)

    for _ in range(5):
        scheduler.run()

    assert order == ["A", "B", "C"]
    assert not scheduler.is_running(seq)


def test_a_step_never_starts_before_its_predecessor_finishes(scheduler):
    m1, m2 = DummyMechanism("m1"), DummyMechanism("m2")
    order = []
    a = _step(m1, "A", order, ticks=3)
    b = _step(m2, "B", order, ticks=1)

    seq = SequentialGroupBuilder().and_then(a).and_then(b).named("Sequence")
    scheduler.schedule(seq)

    scheduler.run()
    assert not scheduler.is_scheduled_or_running(b)

    for _ in range(5):
        scheduler.run()

    assert order == ["A", "B"]


def test_with_automatic_name_joins_step_names():
    m1, m2 = DummyMechanism("m1"), DummyMechanism("m2")
    order = []
    a = _step(m1, "A", order)
    b = _step(m2, "B", order)

    seq = SequentialGroupBuilder().and_then(a).and_then(b).with_automatic_name()

    assert seq.name == "A -> B"


def test_command_and_then_builds_a_two_step_sequence(scheduler):
    m1, m2 = DummyMechanism("m1"), DummyMechanism("m2")
    order = []
    a = _step(m1, "A", order)
    b = _step(m2, "B", order)

    seq = a.and_then(b).named("Sequence")
    scheduler.schedule(seq)

    for _ in range(5):
        scheduler.run()

    assert order == ["A", "B"]


def test_command_sequence_static_factory(scheduler):
    m1, m2 = DummyMechanism("m1"), DummyMechanism("m2")
    order = []
    a = _step(m1, "A", order)
    b = _step(m2, "B", order)

    seq = Command.sequence(a, b).named("Sequence")
    scheduler.schedule(seq)

    for _ in range(5):
        scheduler.run()

    assert order == ["A", "B"]


def test_with_automatic_name_includes_until_condition():
    async def park_body():
        while True:
            await yield_()

    c1 = Command.no_requirements(park_body).named("C1")
    c2 = Command.no_requirements(park_body).named("C2")

    seq = (
        SequentialGroupBuilder()
        .and_then(c1, c2)
        .until(lambda: True)
        .with_automatic_name()
    )

    assert seq.name == "(C1 -> C2 | Until Condition)"


async def _one_tick():
    await yield_()


def _ticking(name):
    return Command.no_requirements(_one_tick).named(name)


def test_single_command_sequence(scheduler):
    command = _ticking("The Command")

    sequence = SequentialGroupBuilder().and_then(command).named("The Sequence")
    scheduler.schedule(sequence)

    # The command starts and yields, and so does the sequence.
    scheduler.run()
    assert scheduler.is_running(sequence)
    assert scheduler.is_running(command)

    # The command completes, and the sequence sees that and exits.
    scheduler.run()
    assert not scheduler.is_running(sequence)
    assert not scheduler.is_running(command)


def test_two_command_sequence_starts_the_second_one_cycle_after_the_first(scheduler):
    c1 = _ticking("C1")
    c2 = _ticking("C2")

    sequence = SequentialGroupBuilder().and_then(c1, c2).named("C1 > C2")
    scheduler.schedule(sequence)

    # c1 is scheduled and starts.
    scheduler.run()
    assert scheduler.is_running(sequence), "the sequence should be running"
    assert scheduler.is_running(c1), "starting the sequence starts the first command"
    assert not scheduler.is_scheduled_or_running(c2), (
        "the second command should wait for the first to complete"
    )

    # c1 completes, the sequence sees that, and schedules c2.
    scheduler.run()
    assert scheduler.is_running(sequence)
    assert not scheduler.is_running(c1), "the first command should have completed"
    assert scheduler.is_scheduled_or_running(c2)

    # c2 completes, and the sequence exits.
    scheduler.run()
    assert not scheduler.is_running(sequence)
    assert not scheduler.is_running(c2)


def test_and_then_with_a_single_command_names_the_sequence():
    c1 = _ticking("C1")

    sequence = SequentialGroupBuilder().and_then(c1).named("Seq")

    assert sequence.name == "Seq"


def test_and_then_with_multiple_commands_runs_them_in_order(scheduler):
    order = []
    m1, m2 = DummyMechanism("m1"), DummyMechanism("m2")
    c1 = _step(m1, "C1", order)
    c2 = _step(m2, "C2", order)

    sequence = SequentialGroupBuilder().and_then(c1, c2).named("Seq")
    scheduler.schedule(sequence)
    for _ in range(5):
        scheduler.run()

    assert sequence.name == "Seq"
    assert order == ["C1", "C2"]


def test_repeated_and_then_runs_the_commands_in_order(scheduler):
    order = []
    m1, m2 = DummyMechanism("m1"), DummyMechanism("m2")
    c1 = _step(m1, "C1", order)
    c2 = _step(m2, "C2", order)

    sequence = SequentialGroupBuilder().and_then(c1).and_then(c2).named("Seq")
    scheduler.schedule(sequence)
    for _ in range(5):
        scheduler.run()

    assert sequence.name == "Seq"
    assert order == ["C1", "C2"]


def test_until_races_the_sequence_against_the_end_condition(scheduler):
    done = False

    async def park_body():
        while True:
            await yield_()

    c1 = Command.no_requirements(park_body).named("C1")

    sequence = SequentialGroupBuilder().and_then(c1).until(lambda: done).named("Seq")
    assert sequence.name == "Seq"

    scheduler.schedule(sequence)
    scheduler.run()
    assert scheduler.is_running(sequence)
    assert scheduler.is_running(c1)

    done = True
    scheduler.run()
    assert not scheduler.is_running(sequence)
    assert not scheduler.is_running(c1)


def test_automatic_name_with_an_empty_group():
    assert SequentialGroupBuilder().with_automatic_name().name == ""


def test_automatic_name_with_one_command():
    c1 = _ticking("C1")
    assert SequentialGroupBuilder().and_then(c1).with_automatic_name().name == "C1"


def test_automatic_name_with_multiple_commands():
    c1, c2 = _ticking("C1"), _ticking("C2")
    sequence = SequentialGroupBuilder().and_then(c1, c2).with_automatic_name()
    assert sequence.name == "C1 -> C2"
