# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import pytest
import wpilib.simulation as simulation

from commandsv3 import CommandCancelled, wait, wait_until, yield_


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
        except Exception:
            caught_wrong_type.append(True)

    coro = body()
    coro.send(None)

    with pytest.raises(CommandCancelled):
        coro.throw(CommandCancelled)

    assert caught_wrong_type == []
