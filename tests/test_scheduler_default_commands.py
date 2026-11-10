# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""Default commands and how their scope interacts with opmodes and commands."""

import pytest

from commands3 import Command, Mechanism, Scheduler, park


class DummyMechanism(Mechanism):
    """A mechanism registered with a specific scheduler."""

    def __init__(self, name: str, scheduler: Scheduler) -> None:
        super().__init__(name)
        self._scheduler = scheduler

    def get_registered_scheduler(self) -> Scheduler:
        return self._scheduler


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


def _scoping_command(mech, default_command, name="Scoping Command"):
    """A command that sets ``default_command`` while it's running."""

    async def body():
        mech.set_default_command(default_command)
        await park()

    return Command.no_requirements(body).named(name)


def test_global_default_command_is_always_used(scheduler, fake_fetcher):
    mech = DummyMechanism("Mech", scheduler)
    default_command = mech.run(park).named("Custom Default Command")

    mech.set_default_command(default_command)
    assert not scheduler.is_scheduled_or_running(default_command)

    scheduler.run()
    assert scheduler.is_running(default_command)

    fake_fetcher.opmode_id = 1
    fake_fetcher.opmode_name = "Opmode 1"

    scheduler.run()
    assert scheduler.is_running(default_command), (
        "the default command should still be running when the opmode changes"
    )


def test_default_command_set_in_opmode_stops(scheduler, fake_fetcher):
    mech = DummyMechanism("Mech", scheduler)
    initial_default_command = mech.idle()
    mech.set_default_command(initial_default_command)

    fake_fetcher.opmode_id = 1
    fake_fetcher.opmode_name = "Opmode 1"

    opmode_scoped = mech.run(park).named("Custom Default Command")
    mech.set_default_command(opmode_scoped)

    scheduler.run()
    assert scheduler.is_running(opmode_scoped)

    # Change opmode. The globally scoped default command should run.
    fake_fetcher.opmode_id = 2
    fake_fetcher.opmode_name = "Opmode 2"
    scheduler.run()
    assert not scheduler.is_running(opmode_scoped)
    assert scheduler.is_running(initial_default_command)


def test_default_command_set_in_command_stops(scheduler):
    mech = DummyMechanism("Mech", scheduler)
    initial_default_command = mech.idle()
    mech.set_default_command(initial_default_command)

    command_scoped = mech.run(park).named("Command-Scoped Default Command")
    scoping_command = _scoping_command(mech, command_scoped)

    scheduler.schedule(scoping_command)
    scheduler.run()
    assert scheduler.is_running(scoping_command)
    assert scheduler.is_running(command_scoped)
    assert not scheduler.is_running(initial_default_command)

    scheduler.cancel(scoping_command)
    scheduler.run()
    assert not scheduler.is_running(scoping_command)
    assert not scheduler.is_running(command_scoped)
    assert scheduler.is_running(initial_default_command)


def test_interrupting_default_command_interrupts_owner(scheduler):
    mech = DummyMechanism("Mech", scheduler)
    initial_default_command = mech.idle()
    mech.set_default_command(initial_default_command)

    command_scoped = mech.run(park).named("Command-Scoped Default Command")
    scoping_command = _scoping_command(mech, command_scoped)
    interruptor = mech.run(park).named("Interruptor")

    scheduler.schedule(scoping_command)
    scheduler.run()
    assert scheduler.is_running(scoping_command)
    assert scheduler.is_running(command_scoped)
    assert not scheduler.is_running(initial_default_command)

    scheduler.schedule(interruptor)
    scheduler.run()
    assert not scheduler.is_running(scoping_command)
    assert not scheduler.is_running(command_scoped)
    assert not scheduler.is_running(initial_default_command)
    assert scheduler.is_running(interruptor)


def test_default_command_stackup(scheduler, fake_fetcher):
    mech = DummyMechanism("Mech", scheduler)
    initial_default_command = mech.idle()
    mech.set_default_command(initial_default_command)

    opmode_scoped = mech.run(park).named("Opmode Scoped Default Command")
    command_scoped = mech.run(park).named("Command-Scoped Default Command")
    scoping_command = _scoping_command(mech, command_scoped)

    fake_fetcher.opmode_id = 1
    fake_fetcher.opmode_name = "Opmode 1"
    mech.set_default_command(opmode_scoped)

    scheduler.run()
    assert scheduler.is_running(opmode_scoped), (
        "the opmode-scoped default command should be active"
    )

    scheduler.schedule(scoping_command)
    scheduler.run()
    assert not scheduler.is_running(opmode_scoped), (
        "the opmode-scoped default command should have stopped"
    )
    assert scheduler.is_running(command_scoped)

    fake_fetcher.opmode_id = 2
    fake_fetcher.opmode_name = "Opmode 2"
    scheduler.run()

    assert not scheduler.is_running(opmode_scoped), (
        "the opmode-scoped default command should stop when the opmode changes"
    )
    assert not scheduler.is_running(scoping_command), (
        "the running opmode-scoped command should stop when the opmode changes"
    )
    assert not scheduler.is_running(command_scoped), (
        "the command-scoped default command should stop when its parent stops"
    )
    assert scheduler.is_running(initial_default_command), (
        "the global default command should be active"
    )


def test_default_command_changing_default_command(scheduler):
    class Alternating(DummyMechanism):
        def make_command1(self) -> Command:
            async def body():
                self.set_default_command(self.make_command2())
                # A one-shot default command won't appear in the running
                # commands, so park to make the change observable.
                await park()

            return self.run(body).named("Command 1")

        def make_command2(self) -> Command:
            async def body():
                self.set_default_command(self.make_command1())
                await park()

            return self.run(body).named("Command 2")

    mech = Alternating("Mech", scheduler)
    mech.set_default_command(mech.make_command1())

    # Command 1 and Command 2 should alternate as the default command.
    for i in range(10):
        scheduler.run()

        expected = "Command 1" if i % 2 == 0 else "Command 2"
        assert [c.name for c in scheduler.get_running_commands_for(mech)] == [expected]

    # Check for leaks. If every call to set_default_command() added a new
    # binding for good, there would be one per loop.
    bindings = scheduler._default_command_bindings[mech]
    assert [b.command.name for b in bindings] == ["Command 1", "Command 2", "Command 1"]

    # The scheduler rebuilds the list as it prunes inactive bindings, so read
    # it again rather than holding the old one.
    scheduler.run()
    bindings = scheduler._default_command_bindings[mech]
    assert [b.command.name for b in bindings] == ["Command 1", "Command 2"]
