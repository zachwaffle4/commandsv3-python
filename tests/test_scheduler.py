# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import pytest

from commandsv3 import (
    Command,
    Mechanism,
    ScheduleResult,
    Scheduler,
    await_,
    await_all,
    await_any,
    fork,
    opmode_fetcher,
    yield_,
)


class FakeOpModeFetcher(opmode_fetcher.OpModeFetcher):
    def __init__(self, name: str = ""):
        self.name = name

    def get_opmode_id(self) -> int:
        return 0

    def get_opmode_name(self) -> str:
        return self.name


@pytest.fixture
def fake_fetcher():
    fetcher = FakeOpModeFetcher()
    opmode_fetcher.set_fetcher(fetcher)
    yield fetcher
    opmode_fetcher.set_fetcher(None)


class DummyMechanism(Mechanism):
    pass


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


async def _noop_body():
    pass


def _forever(mechanism):
    async def body():
        while True:
            await yield_()

    return Command.requiring(mechanism).executing(body)


def test_schedule_starts_queued_then_promoted_on_run(scheduler):
    m = DummyMechanism()
    command = _forever(m).named("Forever")

    result = scheduler.schedule(command)

    assert result == ScheduleResult.SUCCESS
    assert scheduler.is_scheduled(command)
    assert not scheduler.is_running(command)

    scheduler.run()

    assert scheduler.is_running(command)
    assert not scheduler.is_scheduled(command)


def test_schedule_already_running_is_rejected(scheduler):
    m = DummyMechanism()
    command = _forever(m).named("Forever")

    scheduler.schedule(command)
    scheduler.run()

    assert scheduler.schedule(command) == ScheduleResult.ALREADY_RUNNING


def test_one_shot_command_completes_within_a_single_run(scheduler):
    m = DummyMechanism()
    ran = []

    async def body():
        ran.append(True)

    command = Command.requiring(m).executing(body).named("OneShot")
    scheduler.schedule(command)
    scheduler.run()

    assert ran == [True]
    assert not scheduler.is_running(command)


def test_lower_priority_conflicting_command_is_rejected(scheduler):
    m = DummyMechanism()
    running = _forever(m).with_priority(5).named("Running")
    scheduler.schedule(running)
    scheduler.run()

    lower = _forever(m).with_priority(1).named("Lower")
    result = scheduler.schedule(lower)

    assert result == ScheduleResult.LOWER_PRIORITY_THAN_RUNNING_COMMAND
    assert scheduler.is_running(running)
    assert not scheduler.is_scheduled_or_running(lower)


def test_equal_or_higher_priority_conflicting_command_evicts_running_one(scheduler):
    m = DummyMechanism()
    canceled = []
    low = (
        _forever(m)
        .with_priority(1)
        .when_canceled(lambda: canceled.append("low"))
        .named("Low")
    )
    scheduler.schedule(low)
    scheduler.run()

    high = _forever(m).with_priority(1).named("High")
    result = scheduler.schedule(high)
    scheduler.run()

    assert result == ScheduleResult.SUCCESS
    assert not scheduler.is_running(low)
    assert scheduler.is_running(high)
    assert canceled == ["low"]


def test_conflicting_on_deck_commands_last_scheduled_wins(scheduler):
    m = DummyMechanism()
    first = _forever(m).named("First")
    second = _forever(m).named("Second")

    scheduler.schedule(first)
    scheduler.schedule(second)

    assert not scheduler.is_scheduled(first)
    assert scheduler.is_scheduled(second)

    scheduler.run()

    assert scheduler.is_running(second)
    assert not scheduler.is_running(first)


def test_cancel_stops_a_running_command_and_calls_on_cancel(scheduler):
    m = DummyMechanism()
    canceled = []
    command = _forever(m).when_canceled(lambda: canceled.append(True)).named("Forever")
    scheduler.schedule(command)
    scheduler.run()

    scheduler.cancel(command)

    assert not scheduler.is_running(command)
    assert canceled == [True]


def test_cancel_runs_finally_block_in_command_body(scheduler):
    m = DummyMechanism()
    cleanup = []

    async def body():
        try:
            while True:
                await yield_()
        finally:
            cleanup.append(True)

    command = Command.requiring(m).executing(body).named("Cleanup")
    scheduler.schedule(command)
    scheduler.run()

    scheduler.cancel(command)

    assert cleanup == [True]


def test_cannot_cancel_the_currently_mounted_command(scheduler):
    m = DummyMechanism()
    captured = {}

    async def body():
        captured["command"] = command
        with pytest.raises(ValueError):
            scheduler.cancel(command)
        await yield_()

    command = Command.requiring(m).executing(body).named("SelfCancel")
    scheduler.schedule(command)
    scheduler.run()

    assert captured["command"] is command


def test_fork_starts_child_in_the_same_tick(scheduler):
    m1 = DummyMechanism("m1")
    m2 = DummyMechanism("m2")
    child_ran = []

    async def child_body():
        child_ran.append(True)

    child = Command.requiring(m2).executing(child_body).named("Child")

    async def parent_body():
        fork(child)
        await yield_()

    parent = Command.requiring(m1).executing(parent_body).named("Parent")
    scheduler.schedule(parent)
    scheduler.run()

    assert child_ran == [True]


def test_cancelling_parent_cascades_to_forked_child(scheduler):
    m1 = DummyMechanism("m1")
    m2 = DummyMechanism("m2")
    child_canceled = []

    async def child_body():
        while True:
            await yield_()

    child = (
        Command.requiring(m2)
        .executing(child_body)
        .when_canceled(lambda: child_canceled.append(True))
        .named("Child")
    )

    async def parent_body():
        fork(child)
        while True:
            await yield_()

    parent = Command.requiring(m1).executing(parent_body).named("Parent")
    scheduler.schedule(parent)
    scheduler.run()

    assert scheduler.is_running(child)

    scheduler.cancel(parent)

    assert not scheduler.is_running(child)
    assert child_canceled == [True]


def test_await_blocks_until_child_completes(scheduler):
    m1 = DummyMechanism("m1")
    m2 = DummyMechanism("m2")
    order = []

    async def child_body():
        order.append("child running")

    child = Command.requiring(m2).executing(child_body).named("Child")

    async def parent_body():
        await await_(child)
        order.append("parent resumed")

    parent = Command.requiring(m1).executing(parent_body).named("Parent")
    scheduler.schedule(parent)
    scheduler.run()

    assert order == ["child running", "parent resumed"]
    assert not scheduler.is_running(parent)


def test_await_all_waits_for_every_command(scheduler):
    m1 = DummyMechanism("m1")
    m2 = DummyMechanism("m2")
    m3 = DummyMechanism("m3")
    done = []

    async def body_a():
        await yield_()
        done.append("a")

    async def body_b():
        await yield_()
        await yield_()
        done.append("b")

    a = Command.requiring(m2).executing(body_a).named("A")
    b = Command.requiring(m3).executing(body_b).named("B")

    async def parent_body():
        await await_all([a, b])
        done.append("parent")

    parent = Command.requiring(m1).executing(parent_body).named("Parent")
    scheduler.schedule(parent)

    for _ in range(5):
        scheduler.run()

    assert done == ["a", "b", "parent"]


def test_await_any_cancels_the_rest(scheduler):
    m1 = DummyMechanism("m1")
    m2 = DummyMechanism("m2")
    m3 = DummyMechanism("m3")

    async def fast_body():
        pass

    async def slow_body():
        while True:
            await yield_()

    fast = Command.requiring(m2).executing(fast_body).named("Fast")
    slow = Command.requiring(m3).executing(slow_body).named("Slow")

    async def parent_body():
        await await_any([fast, slow])

    parent = Command.requiring(m1).executing(parent_body).named("Parent")
    scheduler.schedule(parent)
    scheduler.run()

    assert not scheduler.is_scheduled_or_running(slow)
    assert not scheduler.is_running(parent)


def test_default_command_runs_when_mechanism_is_idle(scheduler):
    m = DummyMechanism()
    ran = []

    async def default_body():
        while True:
            ran.append(True)
            await yield_()

    default_command = Command.requiring(m).executing(default_body).named("Default")
    scheduler.set_default_command(m, default_command)

    scheduler.run()

    assert scheduler.is_running(default_command)
    assert ran == [True]


def test_default_command_does_not_run_while_mechanism_is_busy(scheduler):
    m = DummyMechanism()
    default_ran = []

    async def default_body():
        while True:
            default_ran.append(True)
            await yield_()

    default_command = Command.requiring(m).executing(default_body).named("Default")
    scheduler.set_default_command(m, default_command)

    busy = _forever(m).with_priority(1).named("Busy")
    scheduler.schedule(busy)
    scheduler.run()

    assert scheduler.is_running(busy)
    assert not scheduler.is_running(default_command)
    assert default_ran == []


def test_set_default_command_requiring_other_mechanisms_raises(scheduler):
    m1 = DummyMechanism("m1")
    m2 = DummyMechanism("m2")

    command = Command.requiring(m1, m2).executing(_noop_body).named("TooMany")

    with pytest.raises(ValueError):
        scheduler.set_default_command(m1, command)


def test_exception_in_command_propagates_and_cancels_ancestors(scheduler):
    m1 = DummyMechanism("m1")
    m2 = DummyMechanism("m2")
    canceled = []

    async def child_body():
        while True:
            await yield_()

    child = (
        Command.requiring(m2)
        .executing(child_body)
        .when_canceled(lambda: canceled.append("child"))
        .named("Child")
    )

    async def parent_body():
        fork(child)
        await yield_()
        raise RuntimeError("boom")

    parent = Command.requiring(m1).executing(parent_body).named("Parent")
    scheduler.schedule(parent)
    scheduler.run()

    with pytest.raises(RuntimeError, match="boom"):
        scheduler.run()

    assert not scheduler.is_running(parent)
    assert not scheduler.is_running(child)
    assert canceled == ["child"]


def test_cancel_all_clears_running_and_queued_commands(scheduler):
    m1 = DummyMechanism("m1")
    m2 = DummyMechanism("m2")
    running = _forever(m1).named("Running")
    queued = _forever(m2).named("Queued")

    scheduler.schedule(running)
    scheduler.run()
    scheduler.schedule(queued)

    scheduler.cancel_all()

    assert not scheduler.is_scheduled_or_running(running)
    assert not scheduler.is_scheduled_or_running(queued)


def test_default_command_set_inside_a_running_command_is_scoped_to_it(scheduler):
    # Ports the "Scoping" example from design-docs/commands-v3.md: a command
    # that doesn't itself require a mechanism can still temporarily override
    # that mechanism's default command for as long as it runs.
    m = DummyMechanism()
    other = DummyMechanism("other")

    global_ran = []

    async def global_default_body():
        while True:
            global_ran.append(True)
            await yield_()

    global_default = (
        Command.requiring(m).executing(global_default_body).named("GlobalDefault")
    )
    scheduler.set_default_command(m, global_default)

    scoped_ran = []

    async def scoped_default_body():
        while True:
            scoped_ran.append(True)
            await yield_()

    scoped_default = (
        Command.requiring(m).executing(scoped_default_body).named("ScopedDefault")
    )

    async def scoping_body():
        scheduler.set_default_command(m, scoped_default)
        while True:
            await yield_()

    scoping_command = Command.requiring(other).executing(scoping_body).named("Scoping")

    scheduler.schedule(scoping_command)
    scheduler.run()

    assert scheduler.is_running(scoped_default)
    assert not scheduler.is_running(global_default)

    scheduler.cancel(scoping_command)
    scheduler.run()

    assert scheduler.is_running(global_default)
    assert not scheduler.is_running(scoped_default)


def test_default_command_scoped_to_opmode_only_runs_while_selected(
    scheduler, fake_fetcher
):
    m = DummyMechanism()
    ran = []

    async def default_body():
        while True:
            ran.append(True)
            await yield_()

    default_command = Command.requiring(m).executing(default_body).named("AutoDefault")
    scheduler.set_default_command_for_opmode("Autonomous", m, default_command)

    fake_fetcher.name = "Teleop"
    scheduler.run()
    assert not scheduler.is_running(default_command)

    fake_fetcher.name = "Autonomous"
    scheduler.run()
    assert scheduler.is_running(default_command)

    fake_fetcher.name = "Teleop"
    scheduler.run()
    assert not scheduler.is_running(default_command)


def test_remove_default_command_drops_the_opmode_scoped_binding(
    scheduler, fake_fetcher
):
    m = DummyMechanism()
    ran = []

    async def default_body():
        while True:
            ran.append(True)
            await yield_()

    default_command = Command.requiring(m).executing(default_body).named("AutoDefault")
    scheduler.set_default_command_for_opmode("Autonomous", m, default_command)
    fake_fetcher.name = "Autonomous"
    scheduler.run()
    assert scheduler.is_running(default_command)

    scheduler.remove_default_command("Autonomous", m)

    assert not scheduler.is_running(default_command)
    assert scheduler.get_default_command_for(m) is None

    scheduler.run()
    assert not scheduler.is_running(default_command)
