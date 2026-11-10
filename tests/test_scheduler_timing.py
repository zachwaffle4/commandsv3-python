# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Timing bookkeeping. ``wpilib.RobotController.get_time()`` reports
nanoseconds, while the scheduler reports
milliseconds, so these pin the conversion rather than just checking that
*some* number comes back.
"""

import pytest
from wpilib import simulation

from commands3 import Command, Mechanism, Scheduler, await_, park, wait, yield_
from commands3 import scheduler as scheduler_module


class DummyMechanism(Mechanism):
    pass


class _FakeClock:
    """Stands in for ``wpilib`` in the scheduler module, with a clock we drive."""

    def __init__(self) -> None:
        self.nanos = 0
        self.step_nanos = 0
        # The scheduler only ever reaches through to RobotController.
        self.RobotController = self

    def get_time(self) -> int:
        now = self.nanos
        self.nanos += self.step_nanos
        return now


@pytest.fixture
def clock(monkeypatch):
    fake = _FakeClock()
    monkeypatch.setattr(scheduler_module, "wpilib", fake)
    return fake


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


def test_last_runtime_is_reported_in_milliseconds(scheduler, clock):
    # Every get_time() call advances the clock by 1 ms worth of nanoseconds,
    # so the start/end pair around run() spans exactly 1 ms.
    clock.step_nanos = 1_000_000

    scheduler.run()

    assert scheduler.last_runtime_ms() == pytest.approx(1.0)


def test_command_runtime_is_reported_in_milliseconds(scheduler, clock):
    clock.step_nanos = 500_000  # 0.5 ms per get_time() call

    mechanism = DummyMechanism()
    command = Command.requiring(mechanism).executing(park).named("Parked")

    scheduler.schedule(command)
    scheduler.run()

    assert scheduler.last_command_runtime_ms(command) == pytest.approx(0.5)
    assert scheduler.total_runtime_ms(command) == pytest.approx(0.5)


def test_total_runtime_accumulates_across_ticks(scheduler, clock):
    clock.step_nanos = 1_000_000

    mechanism = DummyMechanism()

    async def body():
        while True:
            await yield_()

    command = Command.requiring(mechanism).executing(body).named("Looping")

    scheduler.schedule(command)
    scheduler.run()
    scheduler.run()
    scheduler.run()

    assert scheduler.last_command_runtime_ms(command) == pytest.approx(1.0)
    assert scheduler.total_runtime_ms(command) == pytest.approx(3.0)


def test_runtimes_are_negative_one_when_not_running(scheduler):
    mechanism = DummyMechanism()
    command = Command.requiring(mechanism).executing(park).named("Parked")

    assert scheduler.last_command_runtime_ms(command) == -1.0
    assert scheduler.total_runtime_ms(command) == -1.0


def test_last_runtime_is_negative_one_before_the_first_run(scheduler):
    assert scheduler.last_runtime_ms() == -1.0


@pytest.fixture
def paused():
    """Pauses simulated time so ``wait()`` only advances when a test says so."""
    simulation.pause_timing()
    yield
    simulation.resume_timing()


def test_command_awaiting_itself_stalls_without_other_effects(scheduler):
    # It spin-waits on itself, which is equivalent to parking.
    refs = {}

    async def body():
        await await_(refs["command"])

    command = Command.no_requirements(body).named("Self Await")
    refs["command"] = command

    scheduler.schedule(command)
    scheduler.run()

    assert scheduler.is_running(command)


def test_command_deadlock_can_be_broken_by_canceling(scheduler):
    # parent starts, schedules child, then waits for child to exit. child
    # starts and waits for parent to exit. Each run sees one check the other
    # and yield, like two threads spin-waiting on each other.
    refs = {}

    async def parent_body():
        await await_(refs["child"])

    async def child_body():
        await await_(refs["parent"])

    parent = Command.no_requirements(parent_body).named("Parent")
    child = Command.no_requirements(child_body).named("Child")
    refs["parent"], refs["child"] = parent, child

    scheduler.schedule(parent)
    scheduler.run()
    assert scheduler.is_running(parent)
    assert scheduler.is_running(child)

    scheduler.run()
    assert scheduler.is_running(parent)
    assert scheduler.is_running(child)

    # Canceling the parent cancels both.
    scheduler.cancel(parent)
    scheduler.run()
    assert not scheduler.is_running(parent)
    assert not scheduler.is_running(child)


def test_delayed_command_deadlock_is_released_by_canceling_either(scheduler):
    refs = {}
    completed = {"command1": False, "command2": False}

    async def body1():
        await yield_()
        await await_(refs["command2"])
        completed["command1"] = True

    async def body2():
        await yield_()
        await await_(refs["command1"])
        completed["command2"] = True

    command1 = Command.no_requirements(body1).named("Command 1")
    command2 = Command.no_requirements(body2).named("Command 2")
    refs["command1"], refs["command2"] = command1, command2

    scheduler.schedule(command1)
    scheduler.schedule(command2)
    scheduler.run()
    assert scheduler.is_running(command1)
    assert scheduler.is_running(command2)

    scheduler.run()
    assert scheduler.is_running(command1)
    assert scheduler.is_running(command2)

    # Canceling either one lets the other exit.
    scheduler.cancel(command2)
    scheduler.run()
    assert not scheduler.is_running(command1)
    assert not scheduler.is_running(command2)
    assert completed["command1"], "command 1 should finish once command 2 stops"
    assert not completed["command2"], "canceling command 2 should stop it early"


def test_forked_child_runs_once_per_scheduler_run(scheduler):
    run_count = 0

    async def inner_body():
        nonlocal run_count
        run_count += 1
        await yield_()

        run_count += 1
        await yield_()

    inner = Command.no_requirements(inner_body).named("Inner")

    async def outer_body():
        await await_(inner)

    outer = Command.no_requirements(outer_body).named("Outer")

    scheduler.schedule(outer)
    scheduler.run()

    assert run_count == 1


def test_short_wait_waits_one_loop(scheduler, paused):
    completed = False

    async def body():
        nonlocal completed
        await wait(0.001)
        completed = True

    command = Command.no_requirements(body).named("Short Wait")

    scheduler.schedule(command)
    scheduler.run()

    # A full second passes, much longer than the wait period.
    simulation.step_timing(1.0)
    scheduler.run()
    assert completed, "a wait that elapsed between runs should have completed"


def test_short_wait_waits_one_loop_with_fast_period(scheduler, paused):
    completed = False

    async def body():
        nonlocal completed
        await wait(0.001)
        completed = True

    command = Command.no_requirements(body).named("Short Wait")

    scheduler.schedule(command)
    scheduler.run()

    # Half the wait period.
    simulation.step_timing(0.0005)
    scheduler.run()
    assert not completed, "the command should still be waiting for 1 ms"

    # The rest of the wait period.
    simulation.step_timing(0.0005)
    scheduler.run()
    assert completed, "a wait that elapsed between runs should have completed"


def test_awaiting_exits_immediately_without_a_one_loop_delay(scheduler):
    inner_runs = 0

    async def inner_body():
        nonlocal inner_runs
        # Executed immediately when forked.
        inner_runs += 1
        await yield_()

        # Executed again on the next run, after the forking command runs.
        inner_runs += 1

    inner = Command.no_requirements(inner_body).named("Inner")

    async def outer_body():
        await await_(inner)

    outer = Command.no_requirements(outer_body).named("Outer")

    scheduler.schedule(outer)

    # First run: runs outer, forks inner, inner runs to its first yield, and
    # outer yields.
    scheduler.run()
    assert scheduler.is_running(inner)
    assert scheduler.is_running(outer)
    assert inner_runs == 1

    # Second run: runs inner to completion, then outer, which sees that inner
    # is complete and exits. If children ran after their parents, outer would
    # take another run to exit.
    scheduler.run()
    assert not scheduler.is_running(inner)
    assert not scheduler.is_running(outer)
    assert inner_runs == 2
