# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import pytest

from commandsv3 import (
    Command,
    Mechanism,
    Scheduler,
    yield_,
    GLOBAL_SCOPE,
    ForCommand,
    ForOpMode,
    create_narrowest_scope,
)
from commandsv3 import opmode_fetcher


class DummyMechanism(Mechanism):
    pass


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
    scope = ForOpMode("Autonomous")

    assert not scope.active()

    fake_fetcher.name = "Autonomous"
    assert scope.active()

    fake_fetcher.name = "Teleop"
    assert not scope.active()


def test_create_narrowest_scope_prefers_running_command_over_opmode(
    scheduler, fake_fetcher
):
    fake_fetcher.name = "Autonomous"
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


def test_create_narrowest_scope_uses_opmode_when_no_command_running(
    scheduler, fake_fetcher
):
    fake_fetcher.name = "Autonomous"

    scope = create_narrowest_scope(scheduler)

    assert isinstance(scope, ForOpMode)
    assert scope.opmode_name == "Autonomous"


def test_create_narrowest_scope_uses_global_when_neither(scheduler, fake_fetcher):
    fake_fetcher.name = ""

    scope = create_narrowest_scope(scheduler)

    assert scope is GLOBAL_SCOPE
