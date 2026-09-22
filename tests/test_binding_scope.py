# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import hal
import pytest

from commands3 import (
    AUTONOMOUS_MODE_SCOPE,
    GLOBAL_SCOPE,
    TELEOP_MODE_SCOPE,
    UTILITY_MODE_SCOPE,
    Command,
    ForCommand,
    ForOpmode,
    Mechanism,
    RobotModeScope,
    Scheduler,
    create_narrowest_scope,
    yield_,
)

#: Every robot mode that maps to a dedicated scope, and the scope it maps to.
MODE_SCOPES = [
    (hal.RobotMode.AUTONOMOUS, AUTONOMOUS_MODE_SCOPE),
    (hal.RobotMode.TELEOPERATED, TELEOP_MODE_SCOPE),
    (hal.RobotMode.UTILITY, UTILITY_MODE_SCOPE),
]


class DummyMechanism(Mechanism):
    pass


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


async def _forever_body():
    while True:
        await yield_()


def test_global_scope_is_always_active():
    assert GLOBAL_SCOPE.active()


def test_for_command_scope_tracks_whether_the_command_is_running(scheduler):
    m = DummyMechanism()
    command = Command.requiring(m).executing(_forever_body).named("Forever")
    scope = ForCommand(scheduler, command)

    assert not scope.active()

    scheduler.schedule(command)
    scheduler.run()
    assert scope.active()

    scheduler.cancel(command)
    assert not scope.active()


def test_for_opmode_scope_tracks_the_fetcher(fake_fetcher):
    scope = ForOpmode(12345)

    assert not scope.active()

    fake_fetcher.opmode_id = 12345
    assert scope.active()

    fake_fetcher.opmode_id = 54321
    assert not scope.active()


@pytest.mark.parametrize(("mode", "scope"), MODE_SCOPES)
def test_robot_mode_scope_tracks_the_fetcher(fake_fetcher, mode, scope):
    fake_fetcher.robot_mode = hal.RobotMode.UNKNOWN
    assert not scope.active()

    fake_fetcher.robot_mode = mode
    assert scope.active()


def test_create_narrowest_scope_prefers_running_command_over_opmode(
    scheduler, fake_fetcher
):
    fake_fetcher.opmode_id = 12345
    m = DummyMechanism()
    captured = {}

    async def body():
        captured["scope"] = create_narrowest_scope(scheduler)
        await yield_()

    command = Command.requiring(m).executing(body).named("Example")
    scheduler.schedule(command)
    scheduler.run()

    assert isinstance(captured["scope"], ForCommand)
    assert captured["scope"].command is command


def test_create_narrowest_scope_prefers_opmode_over_robot_mode(scheduler, fake_fetcher):
    fake_fetcher.opmode_id = 12345
    fake_fetcher.robot_mode = hal.RobotMode.AUTONOMOUS

    scope = create_narrowest_scope(scheduler)

    assert isinstance(scope, ForOpmode)
    assert scope.opmode_id == 12345


@pytest.mark.parametrize(("mode", "expected"), MODE_SCOPES)
def test_create_narrowest_scope_uses_robot_mode_when_no_opmode(
    scheduler, fake_fetcher, mode, expected
):
    fake_fetcher.robot_mode = mode

    scope = create_narrowest_scope(scheduler)

    assert isinstance(scope, RobotModeScope)
    assert scope is expected


def test_create_narrowest_scope_uses_global_when_neither(scheduler, fake_fetcher):
    fake_fetcher.opmode_id = 0
    fake_fetcher.robot_mode = hal.RobotMode.UNKNOWN

    scope = create_narrowest_scope(scheduler)

    assert scope is GLOBAL_SCOPE
