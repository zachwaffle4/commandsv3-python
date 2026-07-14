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
