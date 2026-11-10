# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import gc
import weakref

import hal
import pytest
from wpilib import simulation

from commands3 import Command, Mechanism, Scheduler, Trigger, await_, park, yield_
from commands3.trigger import _Signal

#: Every robot mode that maps to a dedicated binding scope.
CONCRETE_ROBOT_MODES = [
    hal.RobotMode.AUTONOMOUS,
    hal.RobotMode.TELEOPERATED,
    hal.RobotMode.UTILITY,
]


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


async def _one_tick():
    await yield_()


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


def test_if_true_schedules_a_one_shot_on_every_true_poll(scheduler):
    m = DummyMechanism()
    flag = {"value": False}
    command, ran = _one_shot(m)
    Trigger(lambda: flag["value"], scheduler).if_true(command)

    scheduler.run()
    assert ran == []

    flag["value"] = True
    scheduler.run()
    assert ran == [True]

    scheduler.run()
    assert ran == [True, True]

    flag["value"] = False
    scheduler.run()
    assert ran == [True, True]


def test_if_true_does_not_restart_or_cancel_a_long_running_command(scheduler):
    m = DummyMechanism()
    flag = {"value": True}
    starts = []
    canceled = []

    async def body():
        starts.append(True)
        while True:
            await yield_()

    command = (
        Command.requiring(m)
        .executing(body)
        .when_canceled(lambda: canceled.append(True))
        .named("Long")
    )
    Trigger(lambda: flag["value"], scheduler).if_true(command)

    scheduler.run()
    scheduler.run()
    assert starts == [True]
    assert scheduler.is_running(command)

    flag["value"] = False
    scheduler.run()
    assert scheduler.is_running(command)
    assert canceled == []


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


def test_cached_trigger_keeps_updating_after_its_creation_scope_ends(scheduler):
    flag = {"value": False}
    inner = Command.no_requirements(_one_tick).named("Inner")
    captured = {}

    async def scoping_body():
        trigger = Trigger(lambda: flag["value"], scheduler)
        trigger.on_true(inner)
        captured["trigger"] = trigger
        await _one_tick()

    scheduler.schedule(Command.no_requirements(scoping_body).named("Outer"))
    scheduler.run()
    scheduler.run()
    scheduler.run()
    trigger = captured["trigger"]
    assert not trigger.is_scope_active()

    # Scope has ended, but a trigger the user still holds must keep polling.
    flag["value"] = True
    assert not trigger.get_as_boolean()
    scheduler.run()
    assert trigger.get_as_boolean()
    flag["value"] = False
    scheduler.run()
    assert not trigger.get_as_boolean()


def test_trigger_with_a_live_scope_is_retained_without_user_references(scheduler):
    flag = {"value": False}
    command = _forever(DummyMechanism())

    ref = weakref.ref(Trigger(lambda: flag["value"], scheduler).while_true(command))
    gc.collect()
    assert ref() is not None

    flag["value"] = True
    scheduler.run()
    assert scheduler.is_running(command)


def test_trigger_is_collected_after_its_scope_ends_if_uncached(scheduler, fake_fetcher):
    fake_fetcher.opmode_id = 1
    fake_fetcher.opmode_name = "opmode"
    flag = {"value": False}
    fired = []

    async def body():
        fired.append(True)

    command = Command.no_requirements(body).named("Fires")
    ref = weakref.ref(Trigger(lambda: flag["value"], scheduler).on_true(command))

    scheduler.run()
    gc.collect()
    assert ref() is not None, "still in scope, must not be collected"

    fake_fetcher.opmode_id = 0
    fake_fetcher.opmode_name = ""
    flag["value"] = True
    scheduler.run()  # releases the scheduler's strong reference
    gc.collect()

    assert ref() is None
    scheduler.run()
    assert fired == []


def test_binding_scopes_to_opmode_if_available(scheduler, fake_fetcher):
    fake_fetcher.opmode_id = 12345
    fake_fetcher.opmode_name = "This is an opmode!"
    signal = {"value": False}
    trigger = Trigger(lambda: signal["value"], scheduler)
    command = _forever(DummyMechanism())
    trigger.while_true(command)

    signal["value"] = True
    scheduler.run()
    assert scheduler.is_running(command), "Command should have started when triggered"

    fake_fetcher.opmode_id = 0
    fake_fetcher.opmode_name = ""
    scheduler.run()
    assert not scheduler.is_running(command), (
        "Command should have stopped when opmode exited"
    )


@pytest.mark.parametrize("mode", CONCRETE_ROBOT_MODES)
def test_binding_scopes_to_robot_mode_if_available(scheduler, fake_fetcher, mode):
    fake_fetcher.robot_mode = mode
    signal = {"value": False}
    trigger = Trigger(lambda: signal["value"], scheduler)
    command = _forever(DummyMechanism())
    trigger.while_true(command)

    signal["value"] = True
    scheduler.run()
    assert scheduler.is_running(command), "Command should have started when triggered"

    fake_fetcher.robot_mode = hal.RobotMode.UNKNOWN
    scheduler.run()
    assert not scheduler.is_running(command), (
        "Command should have stopped when robot mode exited"
    )


@pytest.mark.parametrize(
    ("source_mode", "destination_mode"),
    [
        (source, destination)
        for source in CONCRETE_ROBOT_MODES
        for destination in CONCRETE_ROBOT_MODES
        if source is not destination
    ],
)
def test_trigger_created_in_one_mode_survives_transition_to_another(
    scheduler, fake_fetcher, source_mode, destination_mode
):
    # Trigger *objects* are globally scoped even when created in a robot
    # mode, so a trigger cached across a mode change can still be rebound.
    fake_fetcher.robot_mode = source_mode
    signal = {"value": False}
    trigger = Trigger(lambda: signal["value"], scheduler)

    source_command = _forever(DummyMechanism("source"))
    trigger.while_true(source_command)

    signal["value"] = True
    scheduler.run()
    assert scheduler.is_running(source_command)

    fake_fetcher.robot_mode = destination_mode
    scheduler.run()
    assert not scheduler.is_running(source_command), (
        "Source mode binding should be inactive after the transition"
    )

    signal["value"] = False
    scheduler.run()

    destination_command = _forever(DummyMechanism("destination"))
    trigger.while_true(destination_command)

    signal["value"] = True
    scheduler.run()
    assert scheduler.is_running(destination_command), (
        "Trigger should still be active after the transition"
    )

    signal["value"] = False
    scheduler.run()
    assert not scheduler.is_running(destination_command), (
        "Destination mode command should cancel on the falling edge"
    )


async def _park_body():
    await park()


def _parked(name="Command"):
    return Command.no_requirements(_park_body).named(name)


def _counting_one_shot(counter):
    async def body():
        counter.append(1)

    return Command.no_requirements(body).named("One Shot")


def _flickering(signal):
    """A condition that reads true once after being set, then resets itself."""

    def condition():
        value = signal["value"]
        if value:
            signal["value"] = False
        return value

    return condition


def test_while_false_schedules_while_low_and_cancels_on_rising_edge(scheduler):
    signal = {"value": False}
    trigger = Trigger(lambda: signal["value"], scheduler)
    command = _parked()
    trigger.while_false(command)

    scheduler.run()
    assert scheduler.is_running(command), (
        "should be scheduled when the signal starts low"
    )

    signal["value"] = True
    scheduler.run()
    assert not scheduler.is_running(command), "should be canceled on the rising edge"


def test_toggle_on_true_toggles_across_edges(scheduler):
    signal = {"value": False}
    trigger = Trigger(lambda: signal["value"], scheduler)
    command = _parked()
    trigger.toggle_on_true(command)

    scheduler.run()
    assert not scheduler.is_running(command)

    signal["value"] = True
    scheduler.run()
    assert scheduler.is_running(command)

    signal["value"] = False
    scheduler.run()
    assert scheduler.is_running(command)

    signal["value"] = True
    scheduler.run()
    assert not scheduler.is_running(command)


def test_toggle_on_false_toggles_across_edges(scheduler):
    signal = {"value": False}
    trigger = Trigger(lambda: signal["value"], scheduler)
    command = _parked()
    trigger.toggle_on_false(command)

    scheduler.run()
    assert scheduler.is_running(command)

    signal["value"] = True
    scheduler.run()
    assert scheduler.is_running(command)

    signal["value"] = False
    scheduler.run()
    assert not scheduler.is_running(command)


def test_command_scoping(scheduler):
    inner_ran = False
    inner_signal = {"value": False}

    async def inner_body():
        nonlocal inner_ran
        while True:
            inner_ran = True
            await park()

    inner = Command.no_requirements(inner_body).named("Inner")

    async def outer_body():
        Trigger(lambda: inner_signal["value"], scheduler).on_true(inner)
        # If this yielded and exited, the outer command would immediately
        # cancel the on-deck inner command before it could run.
        await park()

    outer = Command.no_requirements(outer_body).named("Outer")

    scheduler.schedule(outer)
    scheduler.run()
    assert not inner_ran, "the bound command shouldn't run before the signal is set"

    inner_signal["value"] = True
    scheduler.run()
    assert inner_ran, "the nested trigger should have run the bound command"

    inner_ran = False
    scheduler.run()
    assert not inner_ran, "the trigger shouldn't have fired again"


def test_scope_going_inactive_cancels_bound_command(scheduler):
    from commands3 import BindingScope, BindingType

    class FlagScope(BindingScope):
        active_flag = True

        def active(self) -> bool:
            return self.active_flag

    scope = FlagScope()
    signal = {"value": False}
    trigger = Trigger(lambda: signal["value"], scheduler)
    command = _parked()
    trigger.add_binding(scope, BindingType.RUN_WHILE_HIGH, command)

    signal["value"] = True
    scheduler.run()
    assert scheduler.is_running(command), "the command should start when triggered"

    scope.active_flag = False
    scheduler.run()
    assert not scheduler.is_running(command), (
        "the command should be canceled when the scope goes inactive"
    )


def test_trigger_from_exiting_command_does_not_fire(scheduler):
    condition = {"value": False}
    triggered_command_ran = False

    async def inner_body():
        nonlocal triggered_command_ran
        triggered_command_ran = True
        await park()

    inner = Command.no_requirements(inner_body).named("Inner")

    async def awaited_body():
        await yield_()
        condition["value"] = True

    awaited = Command.no_requirements(awaited_body).named("Awaited")

    async def outer_body():
        Trigger(lambda: condition["value"], scheduler).on_true(inner)
        await await_(awaited)

    outer = Command.no_requirements(outer_body).named("Outer")

    scheduler.schedule(outer)

    # First run: schedules `awaited`, yields.
    scheduler.run()
    assert scheduler.is_running(outer)
    assert scheduler.is_running(awaited)
    assert [c.name for c in scheduler.get_running_commands()] == ["Outer", "Awaited"]

    # Second run: `awaited` sets the condition and exits, then `outer` sees that
    # and exits too. The trigger is checked on the next run().
    scheduler.run()
    assert scheduler.get_running_commands() == []
    assert condition["value"], "the condition wasn't set"
    assert not triggered_command_ran, "the command was unexpectedly triggered"

    # Third run: the binding fires outside a running command and queues
    # `inner`, but its lifetime is bound to `outer`, which has exited, so it
    # is canceled before it can run.
    scheduler.run()
    assert scheduler.get_running_commands() == []
    assert not triggered_command_ran, "the command was unexpectedly triggered"


def test_rising_edge_signals_step_through_each_poll(scheduler):
    signal = {"value": False}
    base = Trigger(lambda: signal["value"], scheduler)
    rising = base.rising_edge()

    assert (base.cached_signal, base.previous_signal) == (None, None)
    assert (rising.cached_signal, rising.previous_signal) == (None, None)

    scheduler.run()  # the base signal stays low
    assert (base.cached_signal, base.previous_signal) == (_Signal.LOW, None)
    assert (rising.cached_signal, rising.previous_signal) == (_Signal.LOW, None)

    signal["value"] = True
    scheduler.run()  # the base signal goes high
    assert (base.cached_signal, base.previous_signal) == (_Signal.HIGH, _Signal.LOW)
    assert (rising.cached_signal, rising.previous_signal) == (_Signal.HIGH, _Signal.LOW)

    scheduler.run()  # the base signal stays high
    assert (base.cached_signal, base.previous_signal) == (_Signal.HIGH, _Signal.HIGH)
    assert (rising.cached_signal, rising.previous_signal) == (
        _Signal.LOW,
        _Signal.HIGH,
    )


def test_falling_edge_signals_step_through_each_poll(scheduler):
    signal = {"value": False}
    base = Trigger(lambda: signal["value"], scheduler)
    falling = base.falling_edge()

    assert (falling.cached_signal, falling.previous_signal) == (None, None)

    scheduler.run()  # the base signal stays low
    assert (falling.cached_signal, falling.previous_signal) == (_Signal.LOW, None)

    signal["value"] = True
    scheduler.run()  # the base signal goes high
    assert (falling.cached_signal, falling.previous_signal) == (
        _Signal.LOW,
        _Signal.LOW,
    )

    signal["value"] = False
    scheduler.run()  # the base signal goes low
    assert (base.cached_signal, base.previous_signal) == (_Signal.LOW, _Signal.HIGH)
    assert (falling.cached_signal, falling.previous_signal) == (
        _Signal.HIGH,
        _Signal.LOW,
    )

    scheduler.run()  # the base signal stays low
    assert (falling.cached_signal, falling.previous_signal) == (
        _Signal.LOW,
        _Signal.HIGH,
    )


def test_composed_trigger_sees_a_dependency_edge_in_the_same_cycle(scheduler):
    a = {"value": False}
    b = {"value": False}
    base_a = Trigger(lambda: a["value"], scheduler)
    base_b = Trigger(lambda: b["value"], scheduler)

    # Depends on an intermediate trigger that nothing else holds.
    composed = base_a.and_(base_b.rising_edge())
    command = _parked("Cmd")
    composed.on_true(command)

    scheduler.run()  # initializes every signal to low
    assert not scheduler.is_running(command)

    # A is true and B has a rising edge in the same cycle.
    a["value"] = True
    b["value"] = True
    scheduler.run()
    assert scheduler.is_running(command), (
        "the composed trigger should fire when a dependency's rising edge occurs"
    )


def test_deeply_nested_dependencies_update_before_the_composed_trigger(scheduler):
    a = {"value": False}
    b = {"value": False}
    c = {"value": False}
    base_a = Trigger(lambda: a["value"], scheduler)
    base_b = Trigger(lambda: b["value"], scheduler)
    base_c = Trigger(lambda: c["value"], scheduler)

    # baseA AND (baseB.rising_edge() AND baseC.rising_edge())
    nested = base_a.and_(base_b.rising_edge().and_(base_c.rising_edge()))

    scheduler.run()

    a["value"] = True
    b["value"] = True
    c["value"] = True
    scheduler.run()

    assert nested.get_as_boolean(), (
        "the nested trigger should fire when every dependency was updated first"
    )


def test_composed_and_of_two_triggers(scheduler):
    a = {"value": False}
    b = {"value": False}
    both = Trigger(_flickering(a), scheduler).and_(Trigger(_flickering(b), scheduler))

    scheduler.run()
    assert not both.get_as_boolean()

    a["value"] = True
    scheduler.run()
    assert not both.get_as_boolean()

    a["value"] = True
    b["value"] = True
    scheduler.run()
    assert both.get_as_boolean()

    a["value"] = False
    scheduler.run()
    assert not both.get_as_boolean()


def test_composed_and_with_a_condition(scheduler):
    a = {"value": False}
    b = {"value": False}
    both = Trigger(_flickering(a), scheduler).and_(_flickering(b))

    scheduler.run()
    assert not both.get_as_boolean()

    a["value"] = True
    b["value"] = True
    scheduler.run()
    assert both.get_as_boolean()

    b["value"] = False
    scheduler.run()
    assert not both.get_as_boolean()


def test_composed_or_of_two_triggers(scheduler):
    a = {"value": False}
    b = {"value": False}
    either = Trigger(_flickering(a), scheduler).or_(Trigger(_flickering(b), scheduler))

    scheduler.run()
    assert not either.get_as_boolean()

    a["value"] = True
    scheduler.run()
    assert either.get_as_boolean()

    a["value"] = False
    scheduler.run()
    assert not either.get_as_boolean()

    b["value"] = True
    scheduler.run()
    assert either.get_as_boolean()


def test_composed_or_with_a_condition(scheduler):
    a = {"value": False}
    b = {"value": False}
    either = Trigger(_flickering(a), scheduler).or_(_flickering(b))

    scheduler.run()
    assert not either.get_as_boolean()

    b["value"] = True
    scheduler.run()
    assert either.get_as_boolean()


def test_composed_negate(scheduler):
    signal = {"value": False}
    negated = Trigger(_flickering(signal), scheduler).negate()

    scheduler.run()
    assert negated.get_as_boolean()

    signal["value"] = True
    scheduler.run()
    assert not negated.get_as_boolean()


def test_self_composition(scheduler):
    signal = {"value": False}
    trigger = Trigger(_flickering(signal), scheduler)

    self_and = trigger.and_(trigger)
    self_or = trigger.or_(trigger)

    scheduler.run()
    assert not self_and.get_as_boolean()
    assert not self_or.get_as_boolean()

    signal["value"] = True
    scheduler.run()
    assert self_and.get_as_boolean()
    assert self_or.get_as_boolean()


def test_complex_composition(scheduler):
    a = {"value": False}
    b = {"value": False}
    c = {"value": False}
    trigger_a = Trigger(_flickering(a), scheduler)
    trigger_b = Trigger(_flickering(b), scheduler)
    trigger_c = Trigger(_flickering(c), scheduler)

    # (A and B) or (not C)
    composed = trigger_a.and_(trigger_b).or_(trigger_c.negate())

    # A=F, B=F, C=F: (F and F) or (not F) -> T
    scheduler.run()
    assert composed.get_as_boolean()

    # A=T, B=T, C=T: (T and T) or (not T) -> T
    a["value"] = True
    b["value"] = True
    c["value"] = True
    scheduler.run()
    assert composed.get_as_boolean()

    # A=F, B=T, C=T: (F and T) or (not T) -> F
    a["value"] = False
    b["value"] = True
    c["value"] = True
    scheduler.run()
    assert not composed.get_as_boolean()


def test_trigger_does_not_unbind_when_its_command_scope_goes_inactive(scheduler):
    trigger_signal = {"value": False}
    command_ran = False
    trigger_ref = []

    async def inner_body():
        nonlocal command_ran
        command_ran = True

    inner = Command.no_requirements(inner_body).named("Inner")

    async def outer_body():
        trigger = Trigger(lambda: trigger_signal["value"], scheduler)
        trigger_ref.append(trigger)
        trigger.on_true(inner)
        await park()

    outer = Command.no_requirements(outer_body).named("Outer")

    scheduler.schedule(outer)
    scheduler.run()
    assert scheduler.is_running(outer)

    trigger_signal["value"] = True
    scheduler.run()
    assert command_ran

    # Canceling the outer command takes the trigger out of scope.
    scheduler.cancel(outer)
    scheduler.run()
    assert not scheduler.is_running(outer)

    # The trigger keeps updating even though its command bindings are gone.
    assert trigger_ref[0].get_as_boolean()
    trigger_signal["value"] = False
    assert trigger_ref[0].get_as_boolean()  # not until the next poll

    scheduler.run()
    assert not trigger_ref[0].get_as_boolean()


def test_multi_press_fires_after_enough_presses_within_the_window(scheduler):
    signal = {"value": False}
    base = Trigger(lambda: signal["value"], scheduler)
    multi = base.multi_press(3, 1.0)

    def press(advance):
        simulation.step_timing(advance)
        signal["value"] = True
        scheduler.run()

    def release():
        signal["value"] = False
        scheduler.run()

    scheduler.run()
    assert not multi.get_as_boolean(), "should not fire initially"

    # Times below are relative to the start; Java's test starts at 1.0 s.
    press(0.1)  # 0.1 s
    assert not multi.get_as_boolean(), "should not fire after 1 press"
    release()

    press(0.1)  # 0.2 s
    assert not multi.get_as_boolean(), "should not fire after 2 presses"
    release()

    press(0.1)  # 0.3 s
    assert multi.get_as_boolean(), "should fire after 3 presses"
    release()

    # A fourth press at 1.0 s: the 0.1 s press hasn't expired yet.
    press(0.7)
    assert multi.get_as_boolean(), "should still fire with 4 presses in the last second"
    release()

    # At 1.2 s the 0.1 s press has expired (1.1 s elapsed), leaving 3.
    simulation.step_timing(0.2)
    scheduler.run()
    assert multi.get_as_boolean(), "should still fire with 3 presses in the last second"

    # At 1.4 s only the 1.0 s press remains.
    simulation.step_timing(0.2)
    scheduler.run()
    assert not multi.get_as_boolean(), "should not fire after the presses expire"


def test_multi_press_zero_duration_is_always_false(scheduler):
    trigger = Trigger(lambda: True, scheduler)
    zero = trigger.multi_press(1, 0.0)
    scheduler.run()
    assert not zero.get_as_boolean()


def test_multi_press_negative_duration_is_always_false(scheduler):
    trigger = Trigger(lambda: True, scheduler)
    negative = trigger.multi_press(1, -1.0)
    scheduler.run()
    assert not negative.get_as_boolean()


def test_multi_press_zero_press_count_is_always_true(scheduler):
    trigger = Trigger(lambda: True, scheduler)
    zero = trigger.multi_press(0, 1.0)
    scheduler.run()
    assert zero.get_as_boolean()


def test_multi_press_negative_press_count_is_always_true(scheduler):
    trigger = Trigger(lambda: True, scheduler)
    negative = trigger.multi_press(-1, 1.0)
    scheduler.run()
    assert negative.get_as_boolean()


def test_retry_while_true_cancels_a_long_running_command_when_the_signal_falls(
    scheduler,
):
    signal = {"value": False}
    trigger = Trigger(lambda: signal["value"], scheduler)
    command = _parked()
    trigger.retry_while_true(command)

    signal["value"] = True
    scheduler.run()
    assert scheduler.is_running(command), "should be running while the signal is true"

    signal["value"] = False
    scheduler.run()
    assert not scheduler.is_running(command), "should be canceled when the signal falls"


def test_retry_while_true_restarts_a_canceled_long_running_command(scheduler):
    signal = {"value": True}
    trigger = Trigger(lambda: signal["value"], scheduler)
    command = _parked()
    trigger.retry_while_true(command)

    scheduler.run()
    assert scheduler.is_running(command), "should be running initially"

    scheduler.cancel(command)
    scheduler.run()
    assert scheduler.is_running(command), "should be restarted in the next cycle"


def test_retry_while_true_restarts_a_one_shot_every_cycle(scheduler):
    signal = {"value": True}
    trigger = Trigger(lambda: signal["value"], scheduler)
    counter = []
    trigger.retry_while_true(_counting_one_shot(counter))

    scheduler.run()
    assert len(counter) == 1, "should have run once"

    scheduler.run()
    assert len(counter) == 2, "should have run twice"


def test_retry_while_false_cancels_a_long_running_command_when_the_signal_rises(
    scheduler,
):
    signal = {"value": True}
    trigger = Trigger(lambda: signal["value"], scheduler)
    command = _parked()
    trigger.retry_while_false(command)

    signal["value"] = False
    scheduler.run()
    assert scheduler.is_running(command), "should be running while the signal is false"

    signal["value"] = True
    scheduler.run()
    assert not scheduler.is_running(command), "should be canceled when the signal rises"


def test_retry_while_false_restarts_a_canceled_long_running_command(scheduler):
    signal = {"value": False}
    trigger = Trigger(lambda: signal["value"], scheduler)
    command = _parked()
    trigger.retry_while_false(command)

    scheduler.run()
    assert scheduler.is_running(command), "should be running initially"

    scheduler.cancel(command)
    scheduler.run()
    assert scheduler.is_running(command), "should be restarted in the next cycle"


def test_retry_while_false_restarts_a_one_shot_every_cycle(scheduler):
    signal = {"value": False}
    trigger = Trigger(lambda: signal["value"], scheduler)
    counter = []
    trigger.retry_while_false(_counting_one_shot(counter))

    scheduler.run()
    assert len(counter) == 1, "should have run once"

    scheduler.run()
    assert len(counter) == 2, "should have run twice"
