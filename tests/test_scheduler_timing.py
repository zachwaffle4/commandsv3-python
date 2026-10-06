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

from commands3 import Command, Mechanism, Scheduler, park, yield_
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
