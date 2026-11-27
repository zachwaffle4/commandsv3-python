# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import pytest
from wpilib import simulation

from commands3 import (
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
    # Zero-yield members are covered by test_zero_yield_optional_command_runs_once.
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


def test_with_automatic_name_includes_until_condition():
    async def park_body():
        while True:
            await yield_()

    a = Command.no_requirements(park_body).named("A")
    b = Command.no_requirements(park_body).named("B")

    group = (
        ParallelGroupBuilder()
        .requiring(a, b)
        .until(lambda: False)
        .with_automatic_name()
    )

    assert group.name == "((A & B) | Until Condition)"


async def _park_body():
    while True:
        await yield_()


def _parked(name):
    return Command.no_requirements(_park_body).named(name)


def _counting(mechanism, name, ticks, counts):
    async def body():
        for _ in range(ticks):
            await yield_()
            counts[name] += 1

    return Command.requiring(mechanism).executing(body).named(name)


def test_required_commands_all_run_to_completion(scheduler):
    counts = {"C1": 0, "C2": 0}
    c1 = _counting(DummyMechanism("R1"), "C1", 5, counts)
    c2 = _counting(DummyMechanism("R2"), "C2", 10, counts)

    parallel = ParallelGroupBuilder().requiring(c1, c2).named("Parallel")
    scheduler.schedule(parallel)

    # The first run schedules and starts the commands.
    scheduler.run()
    assert scheduler.is_running(parallel)
    assert scheduler.is_running(c1)
    assert scheduler.is_running(c2)

    for i in range(1, 5):
        scheduler.run()
        assert scheduler.is_running(c1)
        assert scheduler.is_running(c2)
        assert counts == {"C1": i, "C2": i}

    # c1 finishes after 5 iterations; c2 continues for another 5.
    for i in range(5, 10):
        scheduler.run()
        assert not scheduler.is_running(c1)
        assert scheduler.is_running(c2)
        assert counts == {"C1": 5, "C2": i}

    # One final run ends c2 and the group.
    assert scheduler.is_running(parallel)
    scheduler.run()
    assert not scheduler.is_running(c1)
    assert not scheduler.is_running(c2)
    assert not scheduler.is_running(parallel)
    assert counts == {"C1": 5, "C2": 10}


def test_race_ends_when_the_first_optional_command_finishes(scheduler):
    counts = {"C1": 0, "C2": 0}
    c1 = _counting(DummyMechanism("R1"), "C1", 5, counts)
    c2 = _counting(DummyMechanism("R2"), "C2", 10, counts)

    race = ParallelGroupBuilder().optional(c1, c2).named("Race")
    scheduler.schedule(race)

    scheduler.run()
    assert scheduler.is_running(race)
    assert scheduler.is_running(c1)
    assert scheduler.is_running(c2)

    for i in range(1, 5):
        scheduler.run()
        assert scheduler.is_running(c1)
        assert scheduler.is_running(c2)
        assert counts == {"C1": i, "C2": i}

    scheduler.run()  # completes c1
    assert not scheduler.is_running(race)
    assert not scheduler.is_running(c1)
    assert not scheduler.is_running(c2)
    assert counts == {"C1": 5, "C2": 5}


def test_nested_groups_run_until_the_inner_command_completes(scheduler):
    counts = {"Command": 0}
    command = _counting(DummyMechanism("mechanism"), "Command", 5, counts)

    inner = ParallelGroupBuilder().requiring(command).named("Inner")
    outer = ParallelGroupBuilder().optional(inner).named("Outer")

    # Scheduling puts only the outer group on deck.
    scheduler.schedule(outer)
    assert scheduler.is_scheduled(outer)
    assert not scheduler.is_scheduled_or_running(inner)
    assert not scheduler.is_scheduled_or_running(command)

    # The first run starts the inner group and the command.
    scheduler.run()
    assert scheduler.is_running(outer)
    assert scheduler.is_running(inner)
    assert scheduler.is_running(command)
    assert counts["Command"] == 0

    for i in range(1, 5):
        scheduler.run()
        assert scheduler.is_running(outer)
        assert scheduler.is_running(inner)
        assert scheduler.is_running(command), f"the command should be running ({i})"
        assert counts["Command"] == i

    # The command completes naturally.
    scheduler.run()
    assert not scheduler.is_running(outer)
    assert not scheduler.is_running(inner)
    assert not scheduler.is_running(command)


def test_automatic_name_of_a_race():
    a, b, c = _parked("A"), _parked("B"), _parked("C")
    group = ParallelGroupBuilder().optional(a, b, c).with_automatic_name()
    assert group.name == "(A | B | C)"


def test_automatic_name_of_a_group_of_required_commands():
    a, b, c = _parked("A"), _parked("B"), _parked("C")
    group = ParallelGroupBuilder().requiring(a, b, c).with_automatic_name()
    assert group.name == "(A & B & C)"


def test_automatic_name_of_a_deadline_group():
    a, b, c = _parked("A"), _parked("B"), _parked("C")
    group = ParallelGroupBuilder().requiring(a).optional(b, c).with_automatic_name()
    assert group.name == "[(A) * (B | C)]"


def test_builder_with_only_optional_commands_runs_all_of_them_and_names_itself(
    scheduler,
):
    a, b = _parked("A"), _parked("B")
    group = ParallelGroupBuilder().optional(a, b).with_automatic_name()

    assert group.name == "(A | B)"
    scheduler.schedule(group)
    scheduler.run()
    assert scheduler.is_running(a)
    assert scheduler.is_running(b)


def test_builder_with_only_required_commands_runs_all_of_them_and_names_itself(
    scheduler,
):
    a, b = _parked("A"), _parked("B")
    group = ParallelGroupBuilder().requiring(a, b).with_automatic_name()

    assert group.name == "(A & B)"
    scheduler.schedule(group)
    scheduler.run()
    assert scheduler.is_running(a)
    assert scheduler.is_running(b)


def _counting_one_shot(mechanism, name, runs):
    # Completes without ever suspending, so it finishes inside the fork() that
    # starts it.
    async def body():
        runs[name] = runs.get(name, 0) + 1

    return Command.requiring(mechanism).executing(body).named(name)


def test_zero_yield_optional_command_runs_once(scheduler):
    runs = {}
    fast = _counting_one_shot(DummyMechanism("m1"), "Fast", runs)
    slow = _forever(DummyMechanism("m2"), "Slow")

    race = ParallelGroupBuilder().optional(fast, slow).named("Race")
    scheduler.schedule(race)
    scheduler.run()

    assert runs == {"Fast": 1}
    assert not scheduler.is_running(race)
    assert not scheduler.is_scheduled_or_running(slow)


def test_race_of_two_zero_yield_commands_runs_each_once(scheduler):
    runs = {}
    a = _counting_one_shot(DummyMechanism("m1"), "A", runs)
    b = _counting_one_shot(DummyMechanism("m2"), "B", runs)

    race = Command.race(a, b).named("Race")
    scheduler.schedule(race)
    scheduler.run()

    assert runs == {"A": 1, "B": 1}
    assert not scheduler.is_running(race)


def test_zero_yield_optional_with_required_runs_once_and_waits(scheduler):
    runs = {}
    counts = {"Required": 0}
    required = _counting(DummyMechanism("m1"), "Required", 3, counts)
    optional = _counting_one_shot(DummyMechanism("m2"), "Optional", runs)

    group = ParallelGroupBuilder().requiring(required).optional(optional).named("G")
    scheduler.schedule(group)

    scheduler.run()
    assert runs == {"Optional": 1}
    assert scheduler.is_running(group)

    for _ in range(3):
        scheduler.run()
    assert runs == {"Optional": 1}
    assert counts == {"Required": 3}
    assert not scheduler.is_running(group)


def test_command_both_required_and_optional_runs_once(scheduler):
    runs = {}
    both = _counting_one_shot(DummyMechanism("m1"), "Both", runs)

    group = ParallelGroupBuilder().requiring(both).optional(both).named("G")
    scheduler.schedule(group)
    scheduler.run()

    assert runs == {"Both": 1}
    assert not scheduler.is_running(group)


def test_with_timeout_does_not_repeat_a_zero_yield_action(scheduler):
    runs = {}
    action = _counting_one_shot(DummyMechanism("m"), "Action", runs)

    command = action.with_timeout(1.0)
    scheduler.schedule(command)
    scheduler.run()

    assert runs == {"Action": 1}
    assert not scheduler.is_running(command)


def test_until_already_true_does_not_repeat_the_action(scheduler):
    runs = {}
    checks = 0

    def condition():
        nonlocal checks
        checks += 1
        return True

    action = _counting_one_shot(DummyMechanism("m"), "Action", runs)
    command = action.until(condition).named("Until")
    scheduler.schedule(command)
    scheduler.run()

    assert runs == {"Action": 1}
    # The condition command is a child too, so it must only run once.
    assert checks == 1
    assert not scheduler.is_running(command)


def test_until_already_true_cancels_a_long_running_action(scheduler):
    action = _forever(DummyMechanism("m"), "Action")
    command = action.until(lambda: True).named("Until")
    scheduler.schedule(command)
    scheduler.run()

    assert not scheduler.is_running(command)
    assert not scheduler.is_scheduled_or_running(action)


def test_builder_with_required_and_optional_commands_runs_all_of_them(scheduler):
    req_a, req_b = _parked("ReqA"), _parked("ReqB")
    opt_x, opt_y = _parked("OptX"), _parked("OptY")

    group = (
        ParallelGroupBuilder()
        .requiring(req_a, req_b)
        .optional(opt_x, opt_y)
        .with_automatic_name()
    )

    assert group.name == "[(ReqA & ReqB) * (OptX | OptY)]"
    scheduler.schedule(group)
    scheduler.run()
    for command in (req_a, req_b, opt_x, opt_y):
        assert scheduler.is_running(command)
