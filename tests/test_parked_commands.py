# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
A command suspended by ``park``, ``wait``, ``wait_until``, ``await_``,
``all_of`` or ``any_of`` isn't resumed (and emits no ``Mounted``/``Yielded``
events) until what it's waiting on is ready. A command that just calls
``yield_()`` is still resumed on every tick.
"""

import pytest
from wpilib import simulation

from commands3 import (
    Command,
    Scheduler,
    WaitResult,
    all_of,
    any_of,
    failing_command,
    park,
    wait,
    wait_until,
    yield_,
)
from commands3 import scheduler_event as se


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


@pytest.fixture(autouse=True)
def paused_time():
    """Pauses simulated time so a test decides exactly how much passes."""
    simulation.pause_timing()
    yield
    simulation.resume_timing()


def _mounts(log, command):
    return sum(1 for e in log.of_type(se.Mounted) if e.command is command)


def _yields(log, command):
    return sum(1 for e in log.of_type(se.Yielded) if e.command is command)


def _forever():
    async def body():
        while True:
            await yield_()

    return Command.no_requirements(body).named("Forever")


def test_a_command_that_yields_is_resumed_every_tick(scheduler, watch_events):
    log = watch_events(scheduler)
    command = _forever()

    scheduler.schedule(command)
    for _ in range(4):
        scheduler.run()

    assert _mounts(log, command) == 4
    assert _yields(log, command) == 4


def test_park_is_never_resumed(scheduler, watch_events):
    log = watch_events(scheduler)
    command = Command.no_requirements(park).named("Parked")

    scheduler.schedule(command)
    for _ in range(5):
        scheduler.run()

    assert scheduler.is_running(command)
    assert _mounts(log, command) == 1
    assert _yields(log, command) == 1


def test_a_parked_command_can_still_be_canceled_and_runs_its_finally_block(scheduler):
    cleaned_up = []

    async def body():
        try:
            await park()
        finally:
            cleaned_up.append(True)

    command = Command.no_requirements(body).named("Parked")
    scheduler.schedule(command)
    scheduler.run()
    scheduler.run()

    scheduler.cancel(command)

    assert not scheduler.is_running(command)
    assert cleaned_up == [True]


def test_wait_is_not_resumed_until_the_time_has_elapsed(scheduler, watch_events):
    log = watch_events(scheduler)
    finished = []

    async def body():
        await wait(1.0)
        finished.append(True)

    command = Command.no_requirements(body).named("Waits")
    scheduler.schedule(command)

    scheduler.run()
    simulation.step_timing(0.5)
    scheduler.run()
    scheduler.run()
    assert _mounts(log, command) == 1
    assert finished == []

    simulation.step_timing(0.5)
    scheduler.run()

    assert _mounts(log, command) == 2
    assert finished == [True]
    assert not scheduler.is_running(command)


def test_wait_until_resumes_on_the_tick_its_condition_becomes_true(
    scheduler, watch_events
):
    log = watch_events(scheduler)
    flag = {"value": False}
    finished = []

    async def body():
        await wait_until(lambda: flag["value"])
        finished.append(True)

    command = Command.no_requirements(body).named("Waits")
    scheduler.schedule(command)
    for _ in range(3):
        scheduler.run()
    assert _mounts(log, command) == 1
    assert finished == []

    flag["value"] = True
    scheduler.run()

    assert _mounts(log, command) == 2
    assert finished == [True]


def test_wait_until_times_out(scheduler, watch_events):
    log = watch_events(scheduler)
    results = []

    async def body():
        results.append(await wait_until(lambda: False, timeout=1.0))

    command = Command.no_requirements(body).named("Waits")
    scheduler.schedule(command)
    scheduler.run()
    simulation.step_timing(0.5)
    scheduler.run()
    assert _mounts(log, command) == 1
    assert results == []

    simulation.step_timing(0.6)
    scheduler.run()

    assert results == [WaitResult.TIMED_OUT]
    assert _mounts(log, command) == 2


def test_wait_until_lets_the_condition_win_a_tie_with_the_timeout(scheduler):
    flag = {"value": False}
    results = []

    async def body():
        results.append(await wait_until(lambda: flag["value"], timeout=1.0))

    scheduler.schedule(Command.no_requirements(body).named("Waits"))
    scheduler.run()

    # Both become true before the command next runs.
    flag["value"] = True
    simulation.step_timing(2.0)
    scheduler.run()

    assert results == [WaitResult.CONDITION_MET]


def test_a_parent_awaiting_a_child_resumes_in_the_tick_the_child_completes(
    scheduler, watch_events
):
    log = watch_events(scheduler)
    done = {"value": False}
    after = []

    async def child_body():
        while not done["value"]:
            await yield_()

    child = Command.no_requirements(child_body).named("Child")

    async def parent_body():
        await child
        after.append(True)

    parent = Command.no_requirements(parent_body).named("Parent")
    scheduler.schedule(parent)
    for _ in range(3):
        scheduler.run()
    assert _mounts(log, parent) == 1
    assert _mounts(log, child) == 3
    assert after == []

    log.events.clear()
    done["value"] = True
    scheduler.run()

    assert [(type(e).__name__, e.command.name) for e in log.events] == [
        ("Mounted", "Child"),
        ("Completed", "Child"),
        ("Mounted", "Parent"),
        ("Completed", "Parent"),
    ]
    assert after == [True]


def test_all_of_waits_for_every_command(scheduler, watch_events):
    log = watch_events(scheduler)
    gates = [{"open": False}, {"open": False}]
    after = []

    def gated(gate, name):
        async def body():
            while not gate["open"]:
                await yield_()

        return Command.no_requirements(body).named(name)

    first, second = gated(gates[0], "First"), gated(gates[1], "Second")

    async def parent_body():
        await all_of([first, second])
        after.append(True)

    parent = Command.no_requirements(parent_body).named("Parent")
    scheduler.schedule(parent)
    scheduler.run()

    gates[0]["open"] = True
    scheduler.run()
    scheduler.run()
    assert after == []
    assert _mounts(log, parent) == 1

    gates[1]["open"] = True
    scheduler.run()

    assert after == [True]
    assert _mounts(log, parent) == 2


def test_any_of_resumes_when_the_first_command_completes_and_cancels_the_rest(
    scheduler, watch_events
):
    log = watch_events(scheduler)
    gate = {"open": False}
    after = []

    async def quick_body():
        while not gate["open"]:
            await yield_()

    quick = Command.no_requirements(quick_body).named("Quick")
    slow = _forever()

    async def parent_body():
        await any_of([quick, slow])
        after.append(True)

    parent = Command.no_requirements(parent_body).named("Parent")
    scheduler.schedule(parent)
    for _ in range(3):
        scheduler.run()
    assert _mounts(log, parent) == 1
    assert after == []

    gate["open"] = True
    scheduler.run()

    assert after == [True]
    assert not scheduler.is_running(slow)
    log.assert_canceled(slow)


def test_a_condition_that_raises_is_attributed_to_its_command(scheduler, watch_events):
    log = watch_events(scheduler)
    calls = []
    cleaned_up = []

    def condition():
        calls.append(True)
        # Fine when the body checks it, then it fails when the scheduler does.
        if len(calls) > 1:
            raise RuntimeError("bad condition")
        return False

    async def body():
        try:
            await wait_until(condition)
        finally:
            cleaned_up.append(True)

    command = Command.no_requirements(body).named("Waits")
    scheduler.schedule(command)
    scheduler.run()

    with pytest.raises(RuntimeError, match="bad condition") as raised:
        scheduler.run()

    assert failing_command(raised.value) is command
    assert not scheduler.is_running(command)
    assert cleaned_up == [True]
    assert any(e.command is command for e in log.of_type(se.CompletedWithError))
