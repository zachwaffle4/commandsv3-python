# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""Sideloaded and periodic functions, run by the scheduler outside any command."""

import hal
import pytest

from commands3 import (
    Command,
    Mechanism,
    Scheduler,
    Trigger,
    fork,
    park,
    wait_until,
    yield_,
)
from commands3 import execution_context as ec


class DummyMechanism(Mechanism):
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


def test_sideload_exception_propagates_and_removes_the_sideload(scheduler):
    runs = 0

    async def body():
        nonlocal runs
        runs += 1
        raise RuntimeError("Bang!")

    scheduler.sideload(body)

    with pytest.raises(RuntimeError, match="Bang!"):
        scheduler.run()

    # A sideload that raised is spent, so it doesn't raise every tick.
    scheduler.run()
    assert runs == 1


def test_sideload_body_must_be_async(scheduler):
    with pytest.raises(TypeError, match="async def"):
        scheduler.sideload(lambda: None)


def test_periodic_sideload(scheduler):
    count = 0

    def increment():
        nonlocal count
        count += 1

    scheduler.add_periodic(increment)
    assert count == 0

    scheduler.run()
    assert count == 1

    scheduler.run()
    assert count == 2


def test_multiple_periodic_sideloads(scheduler):
    periodic_count = 4
    count = 0

    def increment():
        nonlocal count
        count += 1

    for _ in range(periodic_count):
        scheduler.add_periodic(increment)
    assert count == 0

    scheduler.run()
    assert count == periodic_count

    scheduler.run()
    assert count == periodic_count * 2


def test_one_shot_sideload_runs_once(scheduler):
    count = 0

    async def body():
        nonlocal count
        count += 1

    scheduler.sideload(body)
    scheduler.run()
    scheduler.run()
    assert count == 1


def test_sideload_can_yield_across_ticks(scheduler):
    steps = []

    async def body():
        steps.append(1)
        await yield_()
        steps.append(2)

    scheduler.sideload(body)
    scheduler.run()
    assert steps == [1]
    scheduler.run()
    assert steps == [1, 2]


def test_sideload_scheduling_command(scheduler):
    command = Command.no_requirements(_park_body).named("Command")

    async def body():
        fork(command)

    # A one-shot sideload forks a command and exits.
    scheduler.sideload(body)
    scheduler.run()
    assert scheduler.is_running(command), "command should outlast the sideload"


def test_sideload_forked_command_has_no_parent_and_is_queued(scheduler):
    command = Command.no_requirements(_park_body).named("Command")
    seen = {}

    async def body():
        fork(command)
        seen["queued"] = scheduler.is_scheduled(command)
        seen["running"] = scheduler.is_running(command)

    scheduler.sideload(body)
    scheduler.run()

    # Not started on the spot the way a fork inside a command is.
    assert seen == {"queued": True, "running": False}
    assert scheduler.get_parent_of(command) is None


def test_sideload_does_not_mount_a_command(scheduler):
    seen = []

    async def body():
        seen.append(ec.current_state())
        seen.append(scheduler.current_command())

    scheduler.sideload(body)
    scheduler.run()
    assert seen == [None, None]


def test_child_command_cannot_escape_via_sideload(scheduler):
    sideload_ran = False
    child = Command.no_requirements(_park_body).named("Child")

    async def sideload_body():
        nonlocal sideload_ran
        sideload_ran = True
        fork(child)

    async def parent_body():
        # Added inside a command that immediately exits, so the sideload is
        # scoped to a command that's gone before it can ever run.
        scheduler.sideload(sideload_body)

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(parent)
    scheduler.run()
    assert not scheduler.is_scheduled_or_running(parent)
    assert not scheduler.is_scheduled_or_running(child)
    assert not sideload_ran

    scheduler.run()
    assert not sideload_ran
    assert not scheduler.is_running(child)


def test_sideload_is_removed_when_its_command_exits(scheduler):
    count = 0

    def increment():
        nonlocal count
        count += 1

    done = False

    async def parent_body():
        scheduler.add_periodic(increment)
        await wait_until(lambda: done)

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(parent)
    scheduler.run()
    scheduler.run()
    assert count == 1

    done = True
    scheduler.run()  # the parent exits at the end of this tick
    ran_while_parent_lived = count

    scheduler.run()
    scheduler.run()
    assert count == ran_while_parent_lived


def test_sideload_is_removed_when_its_opmode_ends(scheduler, fake_fetcher):
    count = 0

    def increment():
        nonlocal count
        count += 1

    fake_fetcher.opmode_id = 12345
    fake_fetcher.robot_mode = hal.RobotMode.TELEOPERATED
    scheduler.add_periodic(increment)

    scheduler.run()
    assert count == 1

    fake_fetcher.opmode_id = 0
    fake_fetcher.robot_mode = hal.RobotMode.UNKNOWN
    scheduler.run()
    scheduler.run()
    assert count == 1


def test_sideload_canceling_command(scheduler):
    command = Command.no_requirements(_park_body).named("Command")
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.is_running(command)

    async def body():
        scheduler.cancel(command)

    scheduler.sideload(body)
    assert scheduler.is_running(command), "sideload should not have run yet"

    scheduler.run()
    assert not scheduler.is_running(command)


def test_sideload_affects_state_for_trigger_in_same_cycle(scheduler):
    signal = False
    trigger = Trigger(lambda: signal, scheduler)
    command = Command.no_requirements(_park_body).named("Command")
    trigger.on_true(command)

    def set_signal():
        nonlocal signal
        signal = True

    scheduler.add_periodic(set_signal)

    scheduler.run()
    assert signal
    assert scheduler.is_running(command)


def test_sideload_failing_to_fork_does_not_cancel(scheduler):
    mech = DummyMechanism("Mech", scheduler)
    high = Command.requiring(mech).executing(park).with_priority(100).named("High")
    low = Command.requiring(mech).executing(park).with_priority(0).named("Low")

    reached = False
    failed_commands = []

    async def body():
        nonlocal reached
        result = fork(low)
        reached = True
        assert result.failed
        failed_commands.extend(r.command for r in result.failed_commands)

    scheduler.sideload(body)
    scheduler.schedule(high)
    scheduler.run()

    assert reached, "the sideload was terminated before it handled the failure"
    assert failed_commands == [low]


def test_sideload_can_opt_in_to_canceling_on_fork_failure(scheduler):
    mech = DummyMechanism("Mech", scheduler)
    high = Command.requiring(mech).executing(park).with_priority(100).named("High")
    low = Command.requiring(mech).executing(park).with_priority(0).named("Low")

    reached_after = False
    runs = 0

    async def body():
        nonlocal reached_after, runs
        runs += 1
        fork(low, cancel_on_failure=True)
        reached_after = True

    scheduler.sideload(body)
    scheduler.schedule(high)

    # The sideload is canceled quietly rather than raising out of run().
    scheduler.run()
    scheduler.run()
    assert runs == 1
    assert not reached_after


def test_primitives_still_require_a_command_or_sideload():
    with pytest.raises(RuntimeError, match="command or sideload"):
        fork(Command.no_requirements(_park_body).named("Command"))
