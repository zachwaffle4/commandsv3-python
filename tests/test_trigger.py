# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import pytest
import wpilib.simulation as simulation

from commands3 import Command, Mechanism, Scheduler, Trigger, yield_


class DummyMechanism(Mechanism):
    pass


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


@pytest.fixture(autouse=True)
def sim_timing():
    simulation.pause_timing()
    yield
    simulation.resume_timing()


def _one_shot(mechanism):
    ran = []

    async def body():
        ran.append(True)

    return Command.requiring(mechanism).executing(body).named("OneShot"), ran


def _forever(mechanism, on_cancel=None):
    async def body():
        while True:
            await yield_()

    stage = Command.requiring(mechanism).executing(body)
    if on_cancel is not None:
        stage = stage.when_canceled(on_cancel)
    return stage.named("Forever")


def test_on_true_schedules_on_rising_edge(scheduler):
    m = DummyMechanism()
    flag = {"value": False}
    command = _forever(m)
    Trigger(lambda: flag["value"], scheduler).on_true(command)

    scheduler.run()
    assert not scheduler.is_running(command)

    flag["value"] = True
    scheduler.run()
    assert scheduler.is_running(command)


def test_on_false_schedules_on_falling_edge(scheduler):
    m = DummyMechanism()
    flag = {"value": True}
    command = _forever(m)
    Trigger(lambda: flag["value"], scheduler).on_false(command)

    scheduler.run()
    assert not scheduler.is_running(command)

    flag["value"] = False
    scheduler.run()
    assert scheduler.is_running(command)


def test_while_true_cancels_on_falling_edge(scheduler):
    m = DummyMechanism()
    flag = {"value": True}
    canceled = []
    command = _forever(m, on_cancel=lambda: canceled.append(True))
    Trigger(lambda: flag["value"], scheduler).while_true(command)

    scheduler.run()
    assert scheduler.is_running(command)

    flag["value"] = False
    scheduler.run()
    assert not scheduler.is_running(command)
    assert canceled == [True]


def test_while_true_does_not_restart_a_naturally_completed_command(scheduler):
    m = DummyMechanism()
    flag = {"value": False}
    command, ran = _one_shot(m)
    Trigger(lambda: flag["value"], scheduler).while_true(command)

    flag["value"] = True
    scheduler.run()
    assert ran == [True]
    assert not scheduler.is_running(command)

    scheduler.run()
    scheduler.run()
    assert ran == [True]


def test_retry_while_true_restarts_a_naturally_completed_command(scheduler):
    m = DummyMechanism()
    flag = {"value": False}
    ran = []

    async def body():
        ran.append(True)

    command = Command.requiring(m).executing(body).named("Retry")
    Trigger(lambda: flag["value"], scheduler).retry_while_true(command)

    flag["value"] = True
    scheduler.run()
    assert ran == [True]

    scheduler.run()
    assert ran == [True, True]


def test_toggle_on_true_toggles_the_command(scheduler):
    m = DummyMechanism()
    flag = {"value": False}
    command = _forever(m)
    Trigger(lambda: flag["value"], scheduler).toggle_on_true(command)

    flag["value"] = True
    scheduler.run()
    assert scheduler.is_running(command)

    flag["value"] = False
    scheduler.run()
    flag["value"] = True
    scheduler.run()
    assert not scheduler.is_running(command)


def test_and_or_negate_compose_conditions(scheduler):
    a = {"value": False}
    b = {"value": False}

    trigger_a = Trigger(lambda: a["value"], scheduler)
    trigger_b = Trigger(lambda: b["value"], scheduler)

    both = trigger_a.and_(lambda: b["value"])
    either = trigger_a.or_(lambda: b["value"])
    not_a = trigger_a.negate()

    scheduler.run()
    assert not both.get_as_boolean()
    assert not either.get_as_boolean()
    assert not_a.get_as_boolean()

    a["value"] = True
    scheduler.run()
    assert not both.get_as_boolean()
    assert either.get_as_boolean()
    assert not not_a.get_as_boolean()

    b["value"] = True
    scheduler.run()
    assert both.get_as_boolean()
    assert either.get_as_boolean()

    del trigger_b


def test_rising_and_falling_edge_are_only_active_for_one_cycle(scheduler):
    flag = {"value": False}
    base = Trigger(lambda: flag["value"], scheduler)
    rising = base.rising_edge()
    falling = base.falling_edge()

    scheduler.run()
    assert not rising.get_as_boolean()
    assert not falling.get_as_boolean()

    flag["value"] = True
    scheduler.run()
    assert rising.get_as_boolean()

    scheduler.run()
    assert not rising.get_as_boolean()

    flag["value"] = False
    scheduler.run()
    assert falling.get_as_boolean()

    scheduler.run()
    assert not falling.get_as_boolean()


def test_debounce_only_activates_after_the_duration_elapses(scheduler):
    flag = {"value": False}
    debounced = Trigger(lambda: flag["value"], scheduler).debounce(1.0)

    flag["value"] = True
    scheduler.run()
    assert not debounced.get_as_boolean()

    simulation.step_timing(0.5)
    scheduler.run()
    assert not debounced.get_as_boolean()

    simulation.step_timing(0.6)
    scheduler.run()
    assert debounced.get_as_boolean()


def test_unbind_cancels_bound_commands_and_stops_polling(scheduler):
    m = DummyMechanism()
    flag = {"value": True}
    canceled = []
    command = _forever(m, on_cancel=lambda: canceled.append(True))
    trigger = Trigger(lambda: flag["value"], scheduler)
    trigger.while_true(command)

    scheduler.run()
    assert scheduler.is_running(command)

    trigger.unbind()
    assert not scheduler.is_running(command)
    assert canceled == [True]

    # No longer polled - toggling the condition has no further effect.
    flag["value"] = False
    flag["value"] = True
    scheduler.run()
    assert not scheduler.is_running(command)


def test_trigger_created_inside_a_command_unbinds_when_it_stops(scheduler):
    m1 = DummyMechanism("m1")
    m2 = DummyMechanism("m2")
    flag = {"value": True}
    bound_command = _forever(m2)
    captured = {}

    async def scoping_body():
        inner_trigger = Trigger(lambda: flag["value"], scheduler)
        inner_trigger.while_true(bound_command)
        captured["trigger"] = inner_trigger
        while True:
            await yield_()

    scoping_command = Command.requiring(m1).executing(scoping_body).named("Scoping")
    scheduler.schedule(scoping_command)
    scheduler.run()
    # The trigger is created while scoping_command runs for the first time,
    # which happens *after* the event loop is polled this cycle (see
    # Scheduler.run()'s step order) - so it isn't polled until next cycle.
    scheduler.run()

    assert scheduler.is_running(bound_command)

    scheduler.cancel(scoping_command)
    scheduler.run()

    assert not scheduler.is_running(bound_command)
    assert not captured["trigger"].is_scope_active()
