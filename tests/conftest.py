# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Shared test fixtures. Installs a fake ``RobotStateFetcher`` before every
test so the suite never has to hook into driver station simulation or the
HAL.
"""

from collections.abc import Callable
from typing import Any

import hal
import pytest

from commands3 import (
    Command,
    Scheduler,
    SchedulerEvent,
    robot_state_fetcher,
    scheduler_event,
)


class FakeRobotStateFetcher(robot_state_fetcher.RobotStateFetcher):
    """A fetcher whose reported robot state the test controls directly."""

    def __init__(self) -> None:
        self.opmode_id = 0
        self.opmode_name = ""
        self.robot_mode = hal.RobotMode.UNKNOWN
        self.enabled = True

    def get_opmode_id(self) -> int:
        return self.opmode_id

    def get_opmode_name(self) -> str:
        return self.opmode_name

    def get_robot_mode(self) -> hal.RobotMode:
        return self.robot_mode

    def is_enabled(self) -> bool:
        return self.enabled


@pytest.fixture(autouse=True)
def fake_fetcher():
    """Installs a ``FakeRobotStateFetcher`` for the duration of each test."""
    fetcher = FakeRobotStateFetcher()
    robot_state_fetcher.set_fetcher(fetcher)
    yield fetcher
    robot_state_fetcher.set_fetcher(None)


class EventLog:
    """Records every event a scheduler emits, in order."""

    def __init__(self, scheduler: Scheduler) -> None:
        self.events: list[SchedulerEvent] = []
        scheduler.add_event_listener(self.events.append)

    def of_type(self, event_type: type[SchedulerEvent]) -> list[SchedulerEvent]:
        return [e for e in self.events if isinstance(e, event_type)]

    def assert_event(
        self,
        event_type: type[SchedulerEvent],
        predicate: Callable[[Any], bool],
        message: str,
    ) -> None:
        """Asserts some event of ``event_type`` satisfies ``predicate``, in any order."""
        assert any(predicate(e) for e in self.of_type(event_type)), message

    def assert_canceled(self, command: Command) -> None:
        self.assert_event(
            scheduler_event.Canceled,
            lambda e: e.command is command,
            f"{command.name} should have received a Canceled event",
        )


@pytest.fixture
def watch_events():
    """
    A factory that starts recording a scheduler's events::

        log = watch_events(scheduler)
        ...
        log.assert_canceled(command)
    """
    return EventLog
