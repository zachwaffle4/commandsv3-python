# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import pytest
from wpilib import simulation

from commands3 import CommandCancelled, WaitResult, wait, wait_until, yield_


@pytest.fixture(autouse=True)
def sim_timing():
    simulation.pause_timing()
    yield
    simulation.resume_timing()


def _tick(coro):
    """Drives a raw coroutine object by one step, as the scheduler will."""
    try:
        coro.send(None)
        return False
    except StopIteration:
        return True


def test_yield_suspends_exactly_one_step():
    ticks = []

    async def body():
        ticks.append("before")
        await yield_()
        ticks.append("after")

    coro = body()
    assert _tick(coro) is False
    assert ticks == ["before"]
    assert _tick(coro) is True
    assert ticks == ["before", "after"]


def test_wait_blocks_until_duration_elapses():
    done = []

    async def body():
        await wait(1.0)
        done.append(True)

    coro = body()
    assert _tick(coro) is False
    assert not done

    simulation.step_timing(0.5)
    assert _tick(coro) is False
    assert not done

    # Step past (not exactly to) the 1-second mark: the sim clock is
    # absolute-epoch-based, so two 0.5s steps don't always sum to exactly
    # 1.0 in double precision, and hasElapsed(1.0) would flake on the
    # boundary.
    simulation.step_timing(0.6)
    assert _tick(coro) is True
    assert done == [True]


def test_wait_returns_immediately_for_zero_duration():
    async def body():
        await wait(0.0)

    coro = body()
    assert _tick(coro) is True


def test_wait_until_blocks_until_condition_true():
    flag = {"ready": False}
    done = []

    async def body():
        await wait_until(lambda: flag["ready"])
        done.append(True)

    coro = body()
    assert _tick(coro) is False
    assert not done

    flag["ready"] = True
    assert _tick(coro) is True
    assert done == [True]


def test_wait_until_without_timeout_reports_condition_met():
    result = []

    async def body():
        result.append(await wait_until(lambda: True))

    assert _tick(body()) is True
    assert result == [WaitResult.CONDITION_MET]
    assert not result[0].timed_out()


def test_wait_until_with_timeout_reports_condition_met_before_timeout():
    flag = {"ready": False}
    result = []

    async def body():
        result.append(await wait_until(lambda: flag["ready"], timeout=1.0))

    coro = body()
    assert _tick(coro) is False

    simulation.step_timing(0.5)
    flag["ready"] = True
    assert _tick(coro) is True
    assert result == [WaitResult.CONDITION_MET]


def test_wait_until_with_timeout_times_out():
    result = []

    async def body():
        result.append(await wait_until(lambda: False, timeout=1.0))

    coro = body()
    assert _tick(coro) is False

    simulation.step_timing(0.5)
    assert _tick(coro) is False
    assert not result

    simulation.step_timing(0.6)
    assert _tick(coro) is True
    assert result == [WaitResult.TIMED_OUT]
    assert result[0].timed_out()


def test_wait_until_with_timeout_returns_immediately_if_condition_already_met():
    result = []

    async def body():
        result.append(await wait_until(lambda: True, timeout=1.0))

    assert _tick(body()) is True
    assert result == [WaitResult.CONDITION_MET]


def test_wait_until_prefers_condition_over_timeout_when_both_hold():
    flag = {"ready": False}
    result = []

    async def body():
        result.append(await wait_until(lambda: flag["ready"], timeout=1.0))

    coro = body()
    assert _tick(coro) is False

    # Past the timeout, but the condition is also true on this tick.
    simulation.step_timing(1.5)
    flag["ready"] = True
    assert _tick(coro) is True
    assert result == [WaitResult.CONDITION_MET]


def test_cancellation_runs_finally_block():
    cleanup = []

    async def body():
        try:
            await yield_()
            await yield_()
        finally:
            cleanup.append("cleaned up")

    coro = body()
    coro.send(None)
    assert cleanup == []

    with pytest.raises(CommandCancelled):
        coro.throw(CommandCancelled)

    assert cleanup == ["cleaned up"]


def test_cancellation_is_not_caught_by_except_exception():
    caught_wrong_type = []

    async def body():
        try:
            await yield_()
        except Exception:  # noqa: BLE001 - the test is that this does NOT catch CommandCancelled
            caught_wrong_type.append(True)

    coro = body()
    coro.send(None)

    with pytest.raises(CommandCancelled):
        coro.throw(CommandCancelled)

    assert caught_wrong_type == []
