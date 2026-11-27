# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import gc
import weakref

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
    Trigger,
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


# -- Binding lifecycle -----------------------------------------------------


def _one_tick_command(name="OneTick", counter=None):
    async def body():
        await yield_()
        if counter is not None:
            counter[name] = counter.get(name, 0) + 1

    return Command.no_requirements(body).named(name)


def test_completed_global_commands_are_not_retained(scheduler):
    # In the global scope a binding's scope never goes inactive, so nothing
    # but the command finishing can retire it.
    refs = []
    for i in range(200):
        command = _one_tick_command(f"C{i}")
        refs.append(weakref.ref(command))
        scheduler.schedule(command)
        scheduler.run()
        scheduler.run()
        assert not scheduler.is_scheduled_or_running(command)
    del command
    gc.collect()

    assert [ref for ref in refs if ref() is not None] == []


def test_canceled_global_commands_are_not_retained(scheduler):
    command = Command.no_requirements(_forever_body).named("Forever")
    ref = weakref.ref(command)
    scheduler.schedule(command)
    scheduler.run()
    scheduler.cancel(command)
    del command
    gc.collect()

    assert ref() is None


def test_expired_opmode_binding_does_not_cancel_a_new_run(scheduler, fake_fetcher):
    runs = {}
    command = _one_tick_command("Command", runs)

    fake_fetcher.opmode_id = 1
    scheduler.schedule(command)
    scheduler.run()
    scheduler.run()
    assert runs == {"Command": 1}

    # The new opmode schedules the same command object before the next run().
    fake_fetcher.opmode_id = 2
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.is_running(command)
    scheduler.run()
    assert runs == {"Command": 2}


def test_expired_opmode_binding_does_not_cancel_a_run_rescheduled_after_cancel(
    scheduler, fake_fetcher
):
    command = Command.no_requirements(_forever_body).named("Forever")

    fake_fetcher.opmode_id = 1
    scheduler.schedule(command)
    scheduler.run()

    fake_fetcher.opmode_id = 2
    scheduler.cancel(command)
    scheduler.schedule(command)
    scheduler.run()

    assert scheduler.is_running(command)


def test_expired_opmode_still_cancels_its_own_run(scheduler, fake_fetcher):
    command = Command.no_requirements(_forever_body).named("Forever")

    fake_fetcher.opmode_id = 1
    scheduler.schedule(command)
    scheduler.run()

    fake_fetcher.opmode_id = 2
    scheduler.run()

    assert not scheduler.is_scheduled_or_running(command)


def test_expired_opmode_cancels_its_queued_run(scheduler, fake_fetcher):
    command = Command.no_requirements(_forever_body).named("Forever")

    fake_fetcher.opmode_id = 1
    scheduler.schedule(command)
    fake_fetcher.opmode_id = 2
    scheduler.run()

    assert not scheduler.is_scheduled_or_running(command)


def test_global_trigger_binding_keeps_working_after_many_completions(scheduler):
    runs = {}
    command = _one_tick_command("Command", runs)
    pressed = False
    Trigger(lambda: pressed, scheduler).on_true(command)

    for i in range(1, 51):
        pressed = True
        scheduler.run()  # rising edge: schedules and starts
        pressed = False
        scheduler.run()  # completes
        assert runs == {"Command": i}
        assert not scheduler.is_scheduled_or_running(command)


def test_expired_trigger_binding_does_not_cancel_a_run_from_a_later_opmode(
    scheduler, fake_fetcher
):
    command = Command.no_requirements(_forever_body).named("Forever")

    fake_fetcher.opmode_id = 1
    old_pressed = False
    old_trigger = Trigger(lambda: old_pressed, scheduler)
    old_trigger.on_true(command)
    old_pressed = True
    scheduler.run()
    assert scheduler.is_running(command)

    # The next opmode restarts the command before the old trigger is polled
    # and notices its binding has expired.
    fake_fetcher.opmode_id = 2
    scheduler.cancel(command)
    scheduler.schedule(command)
    scheduler.run()
    scheduler.run()

    assert scheduler.is_running(command)
    del old_trigger


def test_canceling_a_command_leaves_its_trigger_binding_in_place(scheduler):
    runs = {}
    command = _one_tick_command("Command", runs)
    pressed = False
    Trigger(lambda: pressed, scheduler).on_true(command)

    pressed = True
    scheduler.run()
    scheduler.cancel(command)
    pressed = False
    scheduler.run()

    pressed = True
    scheduler.run()
    scheduler.run()
    assert runs == {"Command": 1}
