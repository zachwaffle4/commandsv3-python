# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Shared test fixtures. Installs a fake ``RobotStateFetcher`` before every
test so the suite never has to hook into driver station simulation or the
HAL.
"""

import hal
import pytest

from commands3 import robot_state_fetcher


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
