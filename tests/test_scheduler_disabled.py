# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Disabled-mode safety: commands that require a mechanism that isn't
controllable during disabled can't run while the robot is disabled.
"""

import pytest

from commands3 import (
    Command,
    Mechanism,
    RequiresUnsafeMechanisms,
    Scheduler,
    Success,
    await_,
    park,
    wait_until,
)


class DummyMechanism(Mechanism):
    """
    A mechanism registered with a specific scheduler, and controllable during
    disabled only if asked to be.
    """

    def __init__(
        self,
        name: str,
        scheduler: Scheduler,
        controllable_during_disabled: bool = False,
    ) -> None:
        super().__init__(name)
        self._scheduler = scheduler
        self._controllable_during_disabled = controllable_during_disabled

    def get_registered_scheduler(self) -> Scheduler:
        return self._scheduler

    def controllable_during_disabled(self) -> bool:
        return self._controllable_during_disabled


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


def test_mechanisms_are_not_controllable_during_disabled_by_default():
    assert not Mechanism("mech").controllable_during_disabled()


def test_cancels_commands_when_robot_enters_disabled(scheduler, fake_fetcher):
    mech = DummyMechanism("mech", scheduler)
    command = mech.run(park).named("Command")

    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.get_running_commands() == [command]

    fake_fetcher.enabled = False
    scheduler.run()
    assert scheduler.get_running_commands() == [], "Command was not canceled"


def test_cancels_composition_when_robot_enters_disabled(scheduler, fake_fetcher):
    mech = DummyMechanism("mech", scheduler)
    child = mech.run(park).named("Child")

    async def parent_body():
        await await_(child)

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(parent)
    scheduler.run()
    assert scheduler.get_running_commands() == [parent, child]

    fake_fetcher.enabled = False
    scheduler.run()
    assert scheduler.get_running_commands() == [], "Composition was not canceled"


def test_does_not_cancel_safe_commands(scheduler, fake_fetcher):
    mech = DummyMechanism("mech", scheduler, controllable_during_disabled=True)
    safe_command = mech.run(park).named("Safe Command")

    scheduler.schedule(safe_command)
    scheduler.run()
    assert scheduler.get_running_commands() == [safe_command]

    fake_fetcher.enabled = False
    scheduler.run()
    assert scheduler.get_running_commands() == [safe_command], (
        "Safe command should still be running"
    )


def test_cannot_schedule_unsafe_command_in_disabled(scheduler, fake_fetcher):
    mech = DummyMechanism("mech", scheduler)
    command = mech.run(park).named("Command")

    fake_fetcher.enabled = False
    result = scheduler.schedule(command)
    assert result == RequiresUnsafeMechanisms(command, frozenset({mech}))
    assert not result.successful


def test_cancels_composition_when_child_cannot_be_scheduled(scheduler, fake_fetcher):
    mech = DummyMechanism("mech", scheduler)
    child = mech.run(park).named("Command")

    async def parent_body():
        await wait_until(lambda: not fake_fetcher.enabled)
        await await_(child)

    parent = Command.no_requirements(parent_body).named("Parent Command")

    scheduler.schedule(parent)
    scheduler.run()
    assert scheduler.get_running_commands() == [parent]

    fake_fetcher.enabled = False
    scheduler.run()
    assert scheduler.get_running_commands() == [], (
        "Entire composition should have been canceled"
    )


def test_can_schedule_safe_command_in_disabled(scheduler, fake_fetcher):
    mech = DummyMechanism("mech", scheduler, controllable_during_disabled=True)
    safe_command = mech.run(park).named("Safe Command")

    fake_fetcher.enabled = False

    assert scheduler.schedule(safe_command) == Success(safe_command)

    scheduler.run()
    assert scheduler.get_running_commands() == [safe_command]


def test_unsafe_default_commands_cannot_run_in_disabled(scheduler, fake_fetcher):
    mech = DummyMechanism("mech", scheduler)
    command = mech.run(park).named("Command")

    fake_fetcher.enabled = False

    mech.set_default_command(command)
    scheduler.run()
    assert scheduler.get_running_commands() == [], (
        "The default command should not be running"
    )
    assert scheduler.get_default_command_for(mech) is command, (
        "The default command should be set"
    )


def test_robot_disabled_between_queue_and_run(scheduler, fake_fetcher):
    mech = DummyMechanism("mech", scheduler)
    command = mech.run(park).named("Command")

    assert scheduler.schedule(command) == Success(command), (
        "The command should have been scheduled"
    )

    fake_fetcher.enabled = False
    scheduler.run()
    assert scheduler.get_running_commands() == [], (
        "The command should have been canceled"
    )
    assert not scheduler.is_scheduled_or_running(command)


def test_unsafe_default_command_resumes_when_robot_is_enabled(scheduler, fake_fetcher):
    # Skipping the default command while disabled mustn't lose it: it comes
    # back on re-enable.
    mech = DummyMechanism("mech", scheduler)
    command = mech.run(park).named("Command")
    mech.set_default_command(command)

    scheduler.run()
    assert scheduler.get_running_commands() == [command]

    fake_fetcher.enabled = False
    scheduler.run()
    assert scheduler.get_running_commands() == []

    fake_fetcher.enabled = True
    scheduler.run()
    assert scheduler.get_running_commands() == [command]
