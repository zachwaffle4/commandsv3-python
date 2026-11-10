# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Commands that run other commands: compositions without requirements, nested
mechanisms, conflicts between children, and one-shots started inside one run.
"""

import pytest

from commands3 import (
    Command,
    Mechanism,
    Scheduler,
    all_of,
    await_,
    fork,
    park,
    yield_,
)


class DummyMechanism(Mechanism):
    """A mechanism registered with a specific scheduler."""

    def __init__(self, name: str, scheduler: Scheduler) -> None:
        super().__init__(name)
        self._scheduler = scheduler

    def get_registered_scheduler(self) -> Scheduler:
        return self._scheduler


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


async def _park_body():
    await park()


# -- Basics ----------------------------------------------------------------


def test_basic_command_runs_until_its_condition_is_met(scheduler):
    enabled = False
    ran = False

    async def body():
        nonlocal ran
        while True:
            await yield_()
            if enabled:
                break
        ran = True

    command = Command.no_requirements(body).named("Basic Command")

    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.is_running(command), "should be running after being scheduled"

    enabled = True
    scheduler.run()
    assert not scheduler.is_running(command), "should be done once its condition is met"
    assert ran


def test_many_commands_each_advance_once_per_run(scheduler):
    # Every command takes exactly one step per run, in the same thread.
    counter = {"x": 0}
    num_commands = 100
    iterations = 500

    for i in range(num_commands):

        async def body():
            for _ in range(iterations):
                counter["x"] += 1
                await yield_()

        scheduler.schedule(Command.no_requirements(body).named(f"CountCommand[{i}]"))

    for _ in range(iterations):
        scheduler.run()

    assert counter["x"] == num_commands * iterations


def test_run_mechanism(scheduler):
    example = DummyMechanism("Counting", scheduler)
    state = {"x": 0}

    async def count_to_ten():
        state["x"] = 0
        for _ in range(10):
            await yield_()
            state["x"] += 1

    scheduler.schedule(example.run(count_to_ten).named("Count To Ten"))
    for _ in range(10):
        scheduler.run()
    scheduler.run()

    assert state["x"] == 10


# -- Compositions and nested mechanisms --------------------------------------


def test_compositions_do_not_need_requirements(scheduler):
    m1 = DummyMechanism("M1", scheduler)
    m2 = DummyMechanism("m2", scheduler)

    # The group has no requirements, but can schedule children that do.
    async def group_body():
        await all_of(
            [
                m1.run(park).named("M1 Command"),
                m2.run(park).named("M2 Command"),
            ]
        )

    group = Command.no_requirements(group_body).named("Composition")

    scheduler.schedule(group)
    scheduler.run()  # starts the m1 and m2 commands
    assert len(scheduler.get_running_commands()) == 3


def test_nested_mechanisms(scheduler):
    class Superstructure(DummyMechanism):
        def __init__(self) -> None:
            super().__init__("Superstructure", scheduler)
            self.elevator = DummyMechanism("Elevator", scheduler)
            self.arm = DummyMechanism("Arm", scheduler)

            self.arm.set_default_command(self.arm.idle())
            self.elevator.set_default_command(self.elevator.idle())
            self.set_default_command(self.idle())

        def super_command(self) -> Command:
            async def body():
                await await_(self.elevator.run(park).named("Elevator Subcommand"))
                await await_(self.arm.run(park).named("Arm Subcommand"))

            return self.run(body).named("Super Command")

    superstructure = Superstructure()

    scheduler.schedule(superstructure.super_command())
    scheduler.run()
    assert superstructure.arm.get_running_commands() == [
        superstructure.arm.get_default_command()
    ], "the arm should only be running its default command"

    # Scheduling something that requires an in-use inner mechanism cancels the
    # outer command.
    scheduler.schedule(superstructure.elevator.run(park).named("Conflict"))

    scheduler.run()  # schedules the default superstructure command
    scheduler.run()  # starts running the default superstructure command
    assert superstructure.get_running_commands() == [
        superstructure.get_default_command()
    ]


# -- Conflicts between children ----------------------------------------------


def test_compositions_cannot_await_conflicting_commands(scheduler):
    mech = DummyMechanism("The Mechanism", scheduler)

    async def group_body():
        await all_of([mech.run(park).named("First"), mech.run(park).named("Second")])

    group = Command.no_requirements(group_body).named("Group")

    scheduler.schedule(group)

    # Running should attempt to schedule multiple conflicting commands.
    with pytest.raises(ValueError) as raised:
        scheduler.run()

    message = str(raised.value)
    assert "cannot share requirements" in message
    assert "First" in message
    assert "Second" in message
    assert "The Mechanism" in message


def test_inner_command_may_interrupt_other_inner_command(scheduler):
    mechanism = DummyMechanism("The mechanism", scheduler)
    first_ran = False
    second_ran = False

    async def first_body():
        nonlocal first_ran
        first_ran = True
        await park()

    async def second_body():
        nonlocal second_ran
        second_ran = True
        await park()

    first = mechanism.run(first_body).named("First")
    second = mechanism.run(second_body).named("Second")

    async def group_body():
        fork(first)
        fork(second)
        await park()

    group = Command.no_requirements(group_body).named("Group")

    scheduler.schedule(group)
    scheduler.run()

    assert first_ran, "the first child should have run to a yield point"
    assert second_ran, "the second child should have run to a yield point"
    assert not scheduler.is_scheduled_or_running(first), (
        "the first should be interrupted"
    )
    assert scheduler.is_running(second), "the second should still be running"
    assert scheduler.is_running(group), "the group should still be running"


def test_nested_one_shot_compositions_all_run_in_one_cycle(scheduler):
    runs = 0

    def make_one_shot():
        async def body():
            nonlocal runs
            runs += 1

        return Command.no_requirements(body).named("One Shot")

    async def inner_body():
        fork(make_one_shot())

    async def three_body():
        fork(make_one_shot())

    async def two_body():
        fork(make_one_shot())
        fork(Command.no_requirements(three_body).named("3"))

    async def command_body():
        fork(make_one_shot())
        fork(make_one_shot())
        fork(Command.no_requirements(inner_body).named("Inner"))
        fork(Command.no_requirements(two_body).named("2"))

    command = Command.no_requirements(command_body).named("Command")

    scheduler.schedule(command)
    scheduler.run()
    assert runs == 5, "all the one-shot commands should have run"
    assert not scheduler.is_running(command), "the command should exit after one cycle"


def test_child_conflicts_with_higher_priority_top_level(scheduler):
    mechanism = DummyMechanism("mechanism", scheduler)
    top = mechanism.run(park).with_priority(10).named("Top")

    # The child conflicts with, and is lower priority than, the top command, so
    # it isn't scheduled and the parent exits immediately.
    child = mechanism.run(park).named("Child")

    async def parent_body():
        await await_(child)

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(top)
    scheduler.schedule(parent)
    scheduler.run()

    assert scheduler.is_running(top), "the top command should not be interrupted"
    assert not scheduler.is_running(child), "the conflicting child should not run"
    assert not scheduler.is_running(parent), "the child's parent should have exited"


def test_child_conflicts_with_lower_priority_top_level(scheduler):
    mechanism = DummyMechanism("mechanism", scheduler)
    top = mechanism.run(park).with_priority(-10).named("Top")

    # The child conflicts with, and is higher priority than, the top command,
    # so the top command is interrupted.
    child = mechanism.run(park).named("Child")

    async def parent_body():
        await await_(child)

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(top)
    scheduler.schedule(parent)
    scheduler.run()

    assert not scheduler.is_running(top), "the top command should be interrupted"
    assert scheduler.is_running(child), "the conflicting child should be running"
    assert scheduler.is_running(parent), "the child's parent should be running"


# -- Forking -----------------------------------------------------------------


def test_fork_many(scheduler):
    a = Command.no_requirements(_park_body).named("A")
    b = Command.no_requirements(_park_body).named("B")
    c = Command.no_requirements(_park_body).named("C")

    async def body():
        fork(a, b, c)
        await park()

    scheduler.schedule(Command.no_requirements(body).named("Fork Many"))
    scheduler.run()

    assert scheduler.is_running(a)
    assert scheduler.is_running(b)
    assert scheduler.is_running(c)
