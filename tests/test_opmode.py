# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import hal
import pytest
import wpilib
import wpilib.simulation as simulation

from commands3 import (
    Command,
    CommandOpMode,
    CommandRobot,
    Mechanism,
    OpModeTriggers,
    Scheduler,
    Trigger,
    create_auto_opmode,
    create_teleop_opmode,
    create_utility_opmode,
    opmode_fetcher,
    yield_,
)


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


@pytest.fixture(autouse=True)
def reset_default_scheduler():
    # OpModeTriggers/CommandOpModes/CommandRobot are hard-wired to
    # Scheduler.get_default() (matching Java's Scheduler.getDefault()), so
    # reset that shared singleton around each test.
    yield
    scheduler = Scheduler.get_default()
    scheduler.cancel_all()
    scheduler._default_command_bindings.clear()
    scheduler._bound_triggers.clear()
    scheduler._active_bindings.clear()


@pytest.fixture(autouse=True)
def sim_setup():
    simulation.pause_timing()
    yield
    simulation.resume_timing()


def _set_enabled(enabled: bool) -> None:
    simulation.DriverStationSim.set_enabled(enabled)
    simulation.DriverStationSim.notify_new_data()


def test_command_opmode_is_instantiable_and_a_no_op():
    opmode = CommandOpMode()
    opmode.periodic()
    opmode.start()
    opmode.end()
    opmode.disabled_periodic()


def test_opmode_triggers_loaded_reflects_the_fetcher(fake_fetcher):
    triggers = OpModeTriggers("Autonomous")

    Scheduler.get_default().run()
    assert not triggers.loaded().get_as_boolean()

    fake_fetcher.name = "Autonomous"
    Scheduler.get_default().run()
    assert triggers.loaded().get_as_boolean()

    fake_fetcher.name = "Teleop"
    Scheduler.get_default().run()
    assert not triggers.loaded().get_as_boolean()


def test_opmode_triggers_enabled_and_disabled_require_loaded_and_ds_state(fake_fetcher):
    triggers = OpModeTriggers("Autonomous")
    fake_fetcher.name = "Autonomous"

    _set_enabled(True)
    Scheduler.get_default().run()
    assert triggers.enabled().get_as_boolean()
    assert not triggers.disabled().get_as_boolean()

    _set_enabled(False)
    Scheduler.get_default().run()
    assert not triggers.enabled().get_as_boolean()
    assert triggers.disabled().get_as_boolean()

    # Not loaded at all - neither should be true regardless of DS state.
    fake_fetcher.name = "Teleop"
    _set_enabled(True)
    Scheduler.get_default().run()
    assert not triggers.enabled().get_as_boolean()


def test_opmode_triggers_enabled_with_extra_condition(fake_fetcher):
    triggers = OpModeTriggers("Autonomous")
    fake_fetcher.name = "Autonomous"
    _set_enabled(True)

    flag = {"value": False}
    combined = triggers.enabled(Trigger(lambda: flag["value"]))

    Scheduler.get_default().run()
    assert not combined.get_as_boolean()

    flag["value"] = True
    Scheduler.get_default().run()
    assert combined.get_as_boolean()


def test_opmode_triggers_set_and_remove_default_command(fake_fetcher):
    scheduler = Scheduler.get_default()
    m = DummyMechanism()
    triggers = OpModeTriggers("Autonomous")

    async def body():
        while True:
            await yield_()

    command = Command.requiring(m).executing(body).named("AutoDefault")
    triggers.set_default_command(m, command)

    fake_fetcher.name = "Autonomous"
    scheduler.run()
    assert scheduler.is_running(command)

    triggers.remove_default_command(m)
    assert not scheduler.is_running(command)
    assert scheduler.get_default_command_for(m) is None


def test_create_auto_teleop_utility_opmode_register_with_robot_state():
    auto = create_auto_opmode("Test Auto Mode")
    teleop = create_teleop_opmode("Test Teleop Mode")
    utility = create_utility_opmode("Test Utility Mode")

    assert isinstance(auto, OpModeTriggers)
    assert isinstance(teleop, OpModeTriggers)
    assert isinstance(utility, OpModeTriggers)


def test_command_robot_create_auto_opmode_registers_and_returns_triggers():
    class ExampleRobot(CommandRobot):
        pass

    robot = ExampleRobot()
    triggers = robot.create_auto_opmode("Test Robot Auto")

    assert isinstance(triggers, OpModeTriggers)
