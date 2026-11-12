# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
``StateMachine``: setup, transitions, completion handling, callbacks, and what
``build()`` does. A state machine is a builder here, so tests schedule
``machine.build()`` rather than the machine itself.
"""

import re

import pytest

from commands3 import (
    DEFAULT_PRIORITY,
    HIGHEST_PRIORITY,
    Command,
    LowerPriorityThanRunningCommand,
    Mechanism,
    Scheduler,
    StateMachine,
    Trigger,
    failing_command,
    park,
    wait_until,
    yield_,
)
from commands3 import scheduler_event as se


class DummyMechanism(Mechanism):
    pass


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


async def _noop():
    pass


async def _yield_once():
    await yield_()


def _parked(name, mechanism=None):
    if mechanism is not None:
        return mechanism.run(park).named(name)
    return Command.no_requirements(park).named(name)


def _yields_once(name):
    return Command.no_requirements(_yield_once).named(name)


def _one_shot(name):
    return Command.no_requirements(_noop).named(name)


def _running_names(scheduler):
    return [command.name for command in scheduler.get_running_commands()]


def _single_state_machine(command=None):
    machine = StateMachine("State Machine")
    state = machine.add_state(command or _parked("Command"))
    machine.set_initial_state(state)
    return machine


# -- Command attributes ------------------------------------------------------


def test_name():
    assert _single_state_machine().build().name == "State Machine"


def test_default_priority_is_zero():
    assert _single_state_machine().build().priority == DEFAULT_PRIORITY


def test_set_priority_is_respected():
    machine = _single_state_machine()
    machine.set_priority(HIGHEST_PRIORITY)

    assert machine.build().priority == HIGHEST_PRIORITY


def test_requirements_are_empty_by_default():
    assert _single_state_machine().build().requirements == frozenset()


def test_requirements_are_not_inherited_from_state_commands():
    command = _parked("Command", DummyMechanism())

    assert _single_state_machine(command).build().requirements == frozenset()


def test_building_without_an_initial_state_fails():
    machine = StateMachine("State Machine")
    state1 = machine.add_state(_parked("Command 1"))
    state2 = machine.add_state(_parked("Command 2"))
    # machine.set_initial_state(state1)  # Oops, someone forgot.
    state1.switch_to(state2).when_complete()

    message = (
        "State Machine does not have an initial state. "
        "Use .set_initial_state() to provide one."
    )
    with pytest.raises(RuntimeError, match=re.escape(message)):
        machine.build()


def test_initial_state_can_be_overridden(scheduler):
    mech = DummyMechanism()
    command1 = _parked("Command 1", mech)
    command2 = _parked("Command 2", mech)

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    machine.set_initial_state(state1)
    machine.set_initial_state(state2)
    state2.switch_to(state1).when_complete()

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()

    assert scheduler.is_running(command)
    assert scheduler.is_running(command2), "Command 2 is the initial state"
    assert not scheduler.is_running(command1)


# -- Transitions -------------------------------------------------------------


def test_transitions(scheduler):
    signal_a = {"value": False}
    signal_b = {"value": False}

    mech = DummyMechanism()
    command1 = _parked("Command 1", mech)
    command2 = _parked("Command 2", mech)
    command3 = _parked("Command 3", mech)

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    state3 = machine.add_state(command3)
    machine.set_initial_state(state1)
    state1.switch_to(state2).when(lambda: signal_a["value"])
    state2.switch_to(state3).when(lambda: signal_b["value"])

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()
    assert _running_names(scheduler) == ["State Machine", "Command 1"]

    signal_a["value"] = True
    scheduler.run()
    assert _running_names(scheduler) == ["State Machine", "Command 2"]

    signal_b["value"] = True
    scheduler.run()
    assert _running_names(scheduler) == ["State Machine", "Command 3"]


def test_transitions_if_condition_is_already_true_when_entered(scheduler):
    command1 = _parked("Command 1")
    command2 = _parked("Command 2")

    signal = {"value": True}
    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    machine.set_initial_state(state1)
    state1.switch_to(state2).when(lambda: signal["value"])

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()

    assert scheduler.is_running(command)
    assert not scheduler.is_running(command1)
    assert scheduler.is_running(command2), "state 1 should have moved on to state 2"


def test_command_exits(scheduler):
    signal = {"value": False}

    async def waits_for_signal():
        await wait_until(lambda: signal["value"])

    command1 = Command.no_requirements(waits_for_signal).named("Command 1")
    command2 = _parked("Command 2")

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    machine.set_initial_state(state1)
    state1.switch_to(state2).when_complete()
    state2.exit_state_machine().when_complete()

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.is_running(command)
    assert scheduler.is_running(command1)

    signal["value"] = True
    scheduler.run()
    assert scheduler.is_running(command)
    assert not scheduler.is_running(command1), "Command 1 should have ended"
    assert scheduler.is_running(command2), "Command 2 should have started"


def test_state_transitions_to_self(scheduler, watch_events):
    log = watch_events(scheduler)
    signal = {"value": False}
    init_count = {"value": 0}

    async def body():
        init_count["value"] += 1
        await park()

    command = Command.no_requirements(body).named("Command")
    machine = StateMachine("State Machine")
    state = machine.add_state(command)
    machine.set_initial_state(state)
    state.switch_to(state).when(lambda: signal["value"])

    machine_command = machine.build()
    scheduler.schedule(machine_command)
    scheduler.run()
    assert scheduler.is_running(machine_command)
    assert init_count["value"] == 1, "the command should be initialized once"

    signal["value"] = True
    scheduler.run()
    assert scheduler.is_running(machine_command), "the machine should still be running"
    assert init_count["value"] == 2, "the command should have restarted"

    # The signal stays high, but the transition only fires on a rising edge, so
    # it doesn't loop. A parked command isn't resumed, so it adds no events.
    assert [(type(e).__name__, e.command.name) for e in log.events] == [
        # First run
        ("Scheduled", "State Machine"),
        ("Mounted", "State Machine"),
        ("Scheduled", "Command"),
        ("Mounted", "Command"),
        ("Yielded", "Command"),
        ("Yielded", "State Machine"),
        # Second run
        ("Mounted", "State Machine"),
        ("Canceled", "Command"),
        ("Scheduled", "Command"),
        ("Mounted", "Command"),
        ("Yielded", "Command"),
        ("Yielded", "State Machine"),
    ]


def test_one_shot_command_transitions_to_self_on_complete(scheduler):
    count = {"value": 0}

    async def body():
        count["value"] += 1

    command = Command.no_requirements(body).named("Command")
    machine = StateMachine("State Machine")
    state = machine.add_state(command)
    machine.set_initial_state(state)
    state.switch_to(state).when_complete()

    machine_command = machine.build()
    scheduler.schedule(machine_command)
    scheduler.run()

    assert scheduler.is_running(machine_command)
    assert count["value"] == 1, "the command should have run once"


def test_only_the_first_explicit_transition_fires(scheduler):
    signal = {"value": False}
    command1 = _parked("Command 1")
    command2 = _parked("Command 2")
    command3 = _parked("Command 3")

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    state3 = machine.add_state(command3)
    machine.set_initial_state(state1)
    state1.switch_to(state2).when(lambda: signal["value"])
    state1.switch_to(state3).when(lambda: signal["value"])

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.get_running_commands() == [command, command1]

    signal["value"] = True
    scheduler.run()
    assert scheduler.get_running_commands() == [command, command2]


def test_only_the_last_when_complete_transition_fires(scheduler):
    command1 = _yields_once("Command 1")
    command2 = _yields_once("Command 2")
    command3 = _yields_once("Command 3")

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    state3 = machine.add_state(command3)
    machine.set_initial_state(state1)
    state1.switch_to(state2).when_complete()
    state1.switch_to(state3).when_complete()  # replaces the previous transition

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.get_running_commands() == [command, command1]

    scheduler.run()
    assert scheduler.get_running_commands() == [command, command3]


def test_when_complete_and_takes_priority_over_when_complete_if_called_last(scheduler):
    signal = {"value": False}
    command1 = _yields_once("Command 1")
    command2 = _yields_once("Command 2")
    command3 = _yields_once("Command 3")

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    state3 = machine.add_state(command3)
    machine.set_initial_state(state1)
    state1.switch_to(state2).when_complete()
    state1.switch_to(state3).when_complete_and(lambda: signal["value"])

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.get_running_commands() == [command, command1]

    signal["value"] = True
    scheduler.run()
    # Command 2 if when_complete took precedence
    assert scheduler.get_running_commands() == [command, command3]


def test_when_complete_and_takes_priority_over_when_complete_if_called_first(scheduler):
    signal = {"value": False}
    command1 = _yields_once("Command 1")
    command2 = _yields_once("Command 2")
    command3 = _yields_once("Command 3")

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    state3 = machine.add_state(command3)
    machine.set_initial_state(state1)
    state1.switch_to(state3).when_complete_and(lambda: signal["value"])
    state1.switch_to(state2).when_complete()

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.get_running_commands() == [command, command1]

    signal["value"] = True
    scheduler.run()
    # Command 2 if the order they were declared in mattered
    assert scheduler.get_running_commands() == [command, command3]


def test_composing_complete(scheduler):
    signal = {"value": False}
    command1 = _yields_once("Command 1")
    command2 = _parked("Command 2")

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    machine.set_initial_state(state1)
    state1.exit_state_machine().when_complete()
    state1.switch_to(state2).when_complete_and(lambda: signal["value"])

    command = machine.build()

    # First run, signal is low: the state machine exits when the state completes
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.is_running(command)
    assert scheduler.is_running(command1)

    scheduler.run()
    assert not scheduler.is_running(command), "the state machine should have exited"

    # Second run, signal goes high: it switches to state 2 instead of exiting
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.is_running(command)
    assert scheduler.is_running(command1)

    signal["value"] = True
    scheduler.run()
    assert scheduler.is_running(command)
    assert not scheduler.is_running(command1), "Command 1 should have ended"
    assert scheduler.is_running(command2), "Command 2 should have started"


# -- switch_from_any ---------------------------------------------------------


def test_cannot_add_a_state_after_a_no_argument_switch_from_any():
    machine = StateMachine("State Machine")
    state1 = machine.add_state(_parked("Command 1"))
    machine.set_initial_state(state1)
    machine.switch_from_any().to_exit_state_machine().when(lambda: True)

    message = (
        "Cannot add new states to a state machine after switch_from_any() has "
        "been called with no arguments"
    )
    with pytest.raises(RuntimeError, match=re.escape(message)):
        machine.add_state(_parked("Command 2"))


def test_can_add_a_state_after_an_explicit_switch_from_any():
    machine = StateMachine("State Machine")
    state1 = machine.add_state(_parked("Command 1"))
    state2 = machine.add_state(_parked("Command 2"))
    machine.switch_from_any(state1, state2).to_exit_state_machine().when(lambda: True)

    # Adding states after an explicit switch_from_any is permitted
    state3 = machine.add_state(_parked("Command 3"))
    machine.set_initial_state(state1)
    state3.switch_to(state1).when_complete()


def test_can_add_a_state_after_an_explicit_state_transition():
    machine = StateMachine("State Machine")
    state1 = machine.add_state(_parked("Command 1"))
    state2 = machine.add_state(_parked("Command 2"))

    # An early explicit state-to-state transition
    state1.switch_to(state2).when_complete()

    # Adding more states to build another subgraph is permitted
    state3 = machine.add_state(_parked("Command 3"))
    machine.set_initial_state(state1)
    state2.switch_to(state3).when_complete()


def test_switch_from_any(scheduler):
    command1 = _yields_once("Command 1")
    command2 = _parked("Command 2")
    command3 = _parked("Command 3")
    signal = {"value": False}

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    state3 = machine.add_state(command3)
    machine.set_initial_state(state1)
    machine.switch_from_any(state1, state2).to(state3).when(lambda: signal["value"])
    state1.switch_to(state2).when_complete()

    command = machine.build()

    # transition from 1 -> 3
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.is_running(command)
    assert scheduler.is_running(command1)

    signal["value"] = True
    scheduler.run()
    assert scheduler.is_running(command)
    assert not scheduler.is_running(command1), "Command 1 should have ended"
    assert scheduler.is_running(command3), "Command 3 should have started"

    scheduler.cancel(command)
    signal["value"] = False

    # transition from 2 -> 3
    scheduler.schedule(command)
    scheduler.run()  # yield 1
    assert _running_names(scheduler) == ["State Machine", "Command 1"]

    scheduler.run()  # transition 1 -> 2
    assert _running_names(scheduler) == ["State Machine", "Command 2"]

    signal["value"] = True
    scheduler.run()  # transition 2 -> 3
    assert _running_names(scheduler) == ["State Machine", "Command 3"]


# -- Dynamic targets ---------------------------------------------------------


def test_switch_to_a_function_when_complete(scheduler):
    count = {"value": 0}

    async def body():
        count["value"] += 1
        await yield_()

    command1 = Command.no_requirements(body).named("Command 1")
    command2 = _parked("Command 2")
    command3 = _parked("Command 3")

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    state3 = machine.add_state(command3)
    machine.set_initial_state(state1)
    state1.switch_to(lambda: state2 if count["value"] == 1 else state3).when_complete()

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()  # command 1 increments the count and then yields
    assert scheduler.get_running_commands() == [command, command1]

    # Command 1 completes and the state machine moves on. If the function were
    # called while setting up, the count would be 0 and it would pick state 3.
    scheduler.run()
    assert scheduler.get_running_commands() == [command, command2]


def test_switch_to_a_function_with_a_condition(scheduler):
    count = {"value": 0}

    async def body():
        while True:
            # Increment after yielding. Otherwise the condition is checked and
            # the machine immediately moves on within the first tick, and the
            # running command 1 is never observed.
            await yield_()
            count["value"] += 1

    command1 = Command.no_requirements(body).named("Command 1")
    command2 = _parked("Command 2")
    command3 = _parked("Command 3")

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    state3 = machine.add_state(command3)
    machine.set_initial_state(state1)
    state1.switch_to(lambda: state2 if count["value"] == 1 else state3).when(
        lambda: count["value"] == 1
    )

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.get_running_commands() == [command, command1]

    scheduler.run()
    assert scheduler.get_running_commands() == [command, command2]


def test_a_function_returning_none_exits_the_state_machine(scheduler):
    signal = {"value": False}

    machine = StateMachine("State Machine")
    state = machine.add_state(_parked("Command"))
    machine.set_initial_state(state)
    state.switch_to(lambda: None).when(lambda: signal["value"])

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.is_running(command)

    signal["value"] = True
    scheduler.run()
    assert not scheduler.is_running(command)
    assert scheduler.get_running_commands() == []


# -- Enter and exit callbacks ------------------------------------------------


def test_runs_on_enter_for_the_initial_state(scheduler):
    enter_count = {"value": 0}

    machine = StateMachine("State Machine")
    state1 = machine.add_state(_parked("Command 1"))
    state2 = machine.add_state(_parked("Command 2"))
    machine.set_initial_state(state1)
    state1.on_enter(lambda: enter_count.__setitem__("value", enter_count["value"] + 1))
    state1.switch_to(state2).when_complete()

    scheduler.schedule(machine.build())
    scheduler.run()

    assert enter_count["value"] == 1


def test_runs_on_exit_on_transition(scheduler):
    exit_count = {"value": 0}
    signal = {"value": False}

    machine = StateMachine("State Machine")
    state1 = machine.add_state(_parked("Command 1"))
    state2 = machine.add_state(_parked("Command 2"))
    machine.set_initial_state(state1)
    state1.on_exit(lambda: exit_count.__setitem__("value", exit_count["value"] + 1))
    state1.switch_to(state2).when(lambda: signal["value"])

    scheduler.schedule(machine.build())
    scheduler.run()
    assert exit_count["value"] == 0, "on_exit should not have been called"

    signal["value"] = True
    scheduler.run()
    assert exit_count["value"] == 1, "on_exit should have been called"


def test_runs_on_exit_when_complete(scheduler):
    exit_count = {"value": 0}
    command1 = _one_shot("Command 1")

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    machine.set_initial_state(state1)
    state1.on_exit(lambda: exit_count.__setitem__("value", exit_count["value"] + 1))

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()

    assert exit_count["value"] == 1
    assert not scheduler.is_running(command1)
    assert not scheduler.is_running(command), "no transitions, so the machine exits"


def test_on_exit_can_schedule(scheduler):
    mech = DummyMechanism()
    main_mech_command = _parked("Main Mech Command", mech)
    background_mech_command = _parked("Background Mech Command", mech)
    next_state_command = _parked("Next")

    signal = {"value": False}
    machine = StateMachine("State Machine")
    state1 = machine.add_state(main_mech_command)
    state2 = machine.add_state(next_state_command)
    machine.set_initial_state(state1)
    state1.switch_to(state2).when(lambda: signal["value"])
    state1.on_exit(lambda: scheduler.schedule(background_mech_command))

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.is_running(command)
    assert scheduler.is_running(main_mech_command)

    signal["value"] = True
    scheduler.run()
    assert scheduler.is_running(command)
    assert not scheduler.is_running(main_mech_command), "Main Mech should have ended"
    assert scheduler.is_running(background_mech_command), (
        "Background should have started"
    )
    assert scheduler.is_running(next_state_command), "Next state should have started"


def test_runs_on_enter_callbacks_in_insertion_order(scheduler):
    info = []

    machine = StateMachine("State Machine")
    state1 = machine.add_state(_one_shot("Command 1"))
    machine.set_initial_state(state1)
    state1.on_enter(lambda: info.append("on_enter 1"))
    state1.on_enter(lambda: info.append("on_enter 2"))

    scheduler.schedule(machine.build())
    scheduler.run()

    assert info == ["on_enter 1", "on_enter 2"]


def test_runs_on_exit_callbacks_in_insertion_order(scheduler):
    info = []

    machine = StateMachine("State Machine")
    state1 = machine.add_state(_one_shot("Command 1"))  # exits immediately
    machine.set_initial_state(state1)
    state1.on_exit(lambda: info.append("on_exit 1"))
    state1.on_exit(lambda: info.append("on_exit 2"))

    scheduler.schedule(machine.build())
    scheduler.run()

    assert info == ["on_exit 1", "on_exit 2"]


def test_on_enter_sees_the_new_command(scheduler):
    command1 = _parked("Command 1")
    saw = []

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    machine.set_initial_state(state1)
    state1.on_enter(lambda: saw.append(scheduler.is_running(command1)))

    scheduler.schedule(machine.build())
    scheduler.run()

    assert saw == [True], "on_enter should see the command running"


def test_on_exit_with_a_transition_sees_the_exited_command(scheduler):
    command1 = _parked("Command 1")
    command2 = _parked("Command 2")
    saw = []
    signal = {"value": False}

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    machine.set_initial_state(state1)
    state1.on_exit(lambda: saw.append(scheduler.is_running(command1)))
    state1.switch_to(state2).when(lambda: signal["value"])

    scheduler.schedule(machine.build())
    scheduler.run()

    signal["value"] = True
    scheduler.run()

    assert saw == [True], "on_exit should see the exiting command"


def test_on_exit_with_complete_cannot_see_the_exited_command(scheduler):
    # Completion means the command finished on its own, so callbacks run after
    # it has finished and can't see it running.
    command1 = _yields_once("Command 1")
    command2 = _parked("Command 2")
    called = []
    saw = []

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    machine.set_initial_state(state1)

    def on_exit():
        called.append(True)
        saw.append(scheduler.is_running(command1))

    state1.on_exit(on_exit)
    state1.switch_to(state2).when_complete()

    scheduler.schedule(machine.build())
    scheduler.run()  # command yields...
    assert called == [], "on_exit should not have been called yet"

    scheduler.run()  # ...then exits here
    assert called == [True]
    assert saw == [False], "the exited command should be invisible"


def test_led_state_machine_builds(scheduler):
    leds = DummyMechanism()
    idle_animation = leds.run(park).with_priority(-1).named("Default Animation")
    info_animation = leds.run(_yield_once).with_priority(0).named("Info")
    warning_animation = leds.run(_yield_once).with_priority(1).named("Warning")

    normal_priority_event = Trigger(lambda: True, scheduler)
    high_priority_event = Trigger(lambda: True, scheduler)

    machine = StateMachine("State Machine")

    idle_state = machine.add_state(idle_animation)
    info_state = machine.add_state(info_animation)
    warning_state = machine.add_state(warning_animation)

    machine.set_initial_state(idle_state)

    idle_state.switch_to(info_state).when(
        normal_priority_event.and_(high_priority_event.negate())
    )
    idle_state.switch_to(warning_state).when(high_priority_event)

    warning_state.switch_to(info_state).when_complete_and(normal_priority_event)
    info_state.switch_to(warning_state).when_complete_and(high_priority_event)

    machine.switch_from_any().to(warning_state).when(high_priority_event)
    machine.switch_from_any().to(idle_state).when_complete()

    assert machine.build().name == "State Machine"


# -- Behavior specific to the builder ----------------------------------------


def test_build_returns_the_same_command_every_time():
    machine = _single_state_machine()

    assert machine.build() is machine.build()


def test_a_state_machine_with_no_transitions_exits_when_its_state_completes(
    scheduler,
):
    machine = _single_state_machine(_yields_once("Command"))
    command = machine.build()

    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.is_running(command)

    scheduler.run()
    assert not scheduler.is_running(command)


def _built_machine_with_a_pending_transition():
    """A built state machine, with transition builders made before it was built."""
    machine = StateMachine("State Machine")
    state1 = machine.add_state(_parked("Command 1"))
    state2 = machine.add_state(_parked("Command 2"))
    machine.set_initial_state(state1)
    pending = {
        "switch_to": state1.switch_to(state2),
        "exit": state1.exit_state_machine(),
        "any": machine.switch_from_any(state1, state2).to(state2),
    }
    machine.build()
    return machine, state1, state2, pending


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m, s1, s2, p: m.add_state(_parked("Another")),
        lambda m, s1, s2, p: m.set_priority(1),
        lambda m, s1, s2, p: m.set_initial_state(s2),
        lambda m, s1, s2, p: m.switch_from_any(),
        lambda m, s1, s2, p: m.switch_from_any(s1),
        lambda m, s1, s2, p: s1.on_enter(lambda: None),
        lambda m, s1, s2, p: s1.on_exit(lambda: None),
        lambda m, s1, s2, p: s1.switch_to(s2).when(lambda: True),
        lambda m, s1, s2, p: s1.switch_to(s2).when_complete(),
        lambda m, s1, s2, p: s1.switch_to(s2).when_complete_and(lambda: True),
        lambda m, s1, s2, p: s1.exit_state_machine().when(lambda: True),
        lambda m, s1, s2, p: p["switch_to"].when(lambda: True),
        lambda m, s1, s2, p: p["exit"].when_complete(),
        lambda m, s1, s2, p: p["any"].when_complete_and(lambda: True),
    ],
    ids=[
        "add_state",
        "set_priority",
        "set_initial_state",
        "switch_from_any()",
        "switch_from_any(state)",
        "on_enter",
        "on_exit",
        "switch_to().when",
        "switch_to().when_complete",
        "switch_to().when_complete_and",
        "exit_state_machine().when",
        "pending switch_to().when",
        "pending exit_state_machine().when_complete",
        "pending switch_from_any().to().when_complete_and",
    ],
)
def test_nothing_can_be_changed_after_build(mutate):
    machine, state1, state2, pending = _built_machine_with_a_pending_transition()

    with pytest.raises(RuntimeError, match="after build"):
        mutate(machine, state1, state2, pending)


def test_a_state_from_another_state_machine_cannot_be_the_initial_state():
    machine = StateMachine("State Machine")
    other_state = StateMachine("Other").add_state(_parked("Other Command"))

    with pytest.raises(ValueError, match="different state machine"):
        machine.set_initial_state(other_state)


def test_a_state_from_another_state_machine_cannot_be_a_transition_target():
    machine = StateMachine("State Machine")
    state = machine.add_state(_parked("Command"))
    other_state = StateMachine("Other").add_state(_parked("Other Command"))

    with pytest.raises(ValueError, match="different state machine"):
        state.switch_to(other_state)
    with pytest.raises(ValueError, match="different state machine"):
        machine.switch_from_any(state).to(other_state)


def test_a_function_returning_a_state_from_another_machine_fails_when_it_fires(
    scheduler,
):
    other_state = StateMachine("Other").add_state(_parked("Other Command"))
    signal = {"value": False}

    machine = StateMachine("State Machine")
    state = machine.add_state(_parked("Command"))
    machine.set_initial_state(state)
    state.switch_to(lambda: other_state).when(lambda: signal["value"])

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()

    signal["value"] = True
    with pytest.raises(
        RuntimeError, match="does not belong to this state machine"
    ) as raised:
        scheduler.run()

    assert failing_command(raised.value) is command


def test_a_trigger_can_be_a_transition_condition(scheduler):
    flag = {"value": False}
    trigger = Trigger(lambda: flag["value"], scheduler)
    command1 = _parked("Command 1")
    command2 = _parked("Command 2")

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    machine.set_initial_state(state1)
    state1.switch_to(state2).when(trigger)

    scheduler.schedule(machine.build())
    scheduler.run()
    assert scheduler.is_running(command1)

    flag["value"] = True
    scheduler.run()  # the trigger polls, then the machine sees its new value
    assert scheduler.is_running(command2)
    assert not scheduler.is_running(command1)


def test_a_trigger_can_be_a_when_complete_and_condition(scheduler):
    flag = {"value": True}
    trigger = Trigger(lambda: flag["value"], scheduler)
    command1 = _yields_once("Command 1")
    command2 = _parked("Command 2")

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    machine.set_initial_state(state1)
    state1.switch_to(state2).when_complete_and(trigger)

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()
    scheduler.run()

    assert scheduler.get_running_commands() == [command, command2]


def test_when_complete_and_replaces_an_earlier_one_with_the_same_condition_object(
    scheduler,
):
    def condition():
        return True

    command1 = _yields_once("Command 1")
    command2 = _yields_once("Command 2")
    command3 = _yields_once("Command 3")

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    state3 = machine.add_state(command3)
    machine.set_initial_state(state1)
    state1.switch_to(state2).when_complete_and(condition)
    state1.switch_to(state3).when_complete_and(condition)  # replaces the first

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()
    scheduler.run()

    assert scheduler.get_running_commands() == [command, command3]


def test_when_complete_and_keeps_both_if_the_condition_objects_differ(scheduler):
    command1 = _yields_once("Command 1")
    command2 = _yields_once("Command 2")
    command3 = _yields_once("Command 3")

    machine = StateMachine("State Machine")
    state1 = machine.add_state(command1)
    state2 = machine.add_state(command2)
    state3 = machine.add_state(command3)
    machine.set_initial_state(state1)
    state1.switch_to(state2).when_complete_and(lambda: True)
    state1.switch_to(state3).when_complete_and(lambda: True)

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()
    scheduler.run()

    # Both apply, and the first declared is checked first.
    assert scheduler.get_running_commands() == [command, command2]


def test_a_transition_shared_between_states_shares_its_edge_detection(scheduler):
    # One transition object serves every state in switch_from_any(a, b), and
    # it remembers the condition's last value even across visits. So a
    # condition that is still high when a state is re-entered doesn't fire
    # again until it has dropped and risen. Deliberate; see the plan notes.
    sig = {"value": False}
    back = {"value": False}
    command_a = _parked("A")
    command_b = _parked("B")
    command_c = _parked("C")

    machine = StateMachine("State Machine")
    state_a = machine.add_state(command_a)
    state_b = machine.add_state(command_b)
    state_c = machine.add_state(command_c)
    machine.set_initial_state(state_a)
    machine.switch_from_any(state_a, state_b).to(state_c).when(lambda: sig["value"])
    state_c.switch_to(state_b).when(lambda: back["value"])

    scheduler.schedule(machine.build())
    scheduler.run()
    assert scheduler.is_running(command_a)

    sig["value"] = True
    scheduler.run()
    assert scheduler.is_running(command_c)

    back["value"] = True
    scheduler.run()
    # Back in B with the condition still high. B's own copy of the transition
    # would fire at once; the shared one has already seen it high.
    assert scheduler.is_running(command_b)

    scheduler.run()
    assert scheduler.is_running(command_b)

    sig["value"] = False
    scheduler.run()
    sig["value"] = True
    scheduler.run()
    assert scheduler.is_running(command_c)


def test_state_commands_inherit_the_state_machine_priority(scheduler):
    mech = DummyMechanism()
    state_command = _parked("State", mech)  # default priority
    intruder = mech.run(park).with_priority(3).named("Intruder")

    machine = StateMachine("State Machine")
    machine.set_priority(5)
    state = machine.add_state(state_command)
    machine.set_initial_state(state)

    scheduler.schedule(machine.build())
    scheduler.run()
    result = scheduler.schedule(intruder)

    assert isinstance(result, LowerPriorityThanRunningCommand)
    assert scheduler.is_running(state_command)
    assert not scheduler.is_running(intruder)


def test_without_a_state_machine_priority_a_higher_priority_command_interrupts(
    scheduler,
):
    mech = DummyMechanism()
    state_command = _parked("State", mech)
    intruder = mech.run(park).with_priority(3).named("Intruder")

    scheduler.schedule(_single_state_machine(state_command).build())
    scheduler.run()
    scheduler.schedule(intruder)
    scheduler.run()

    assert not scheduler.is_running(state_command)
    assert scheduler.is_running(intruder)


def test_a_state_command_that_cannot_start_cancels_the_state_machine(
    scheduler, watch_events
):
    log = watch_events(scheduler)
    mech = DummyMechanism()
    blocker = mech.run(park).with_priority(10).named("Blocker")
    state_command = _parked("State", mech)  # lower priority, same mechanism

    scheduler.schedule(blocker)
    scheduler.run()

    command = _single_state_machine(state_command).build()
    scheduler.schedule(command)
    scheduler.run()  # a fork failure is handled by the scheduler; it doesn't raise

    assert not scheduler.is_scheduled_or_running(command)
    assert not scheduler.is_scheduled_or_running(state_command)
    assert scheduler.is_running(blocker)
    failures = log.of_type(se.ForkFailure)
    assert [e.command for e in failures] == [command]


def test_canceling_the_state_machine_cancels_the_current_state_without_exit_callbacks(
    scheduler,
):
    exits = []
    state_command = _parked("State")

    machine = StateMachine("State Machine")
    state = machine.add_state(state_command)
    machine.set_initial_state(state)
    state.on_exit(lambda: exits.append(True))

    command = machine.build()
    scheduler.schedule(command)
    scheduler.run()
    scheduler.cancel(command)

    assert not scheduler.is_scheduled_or_running(state_command)
    assert exits == [], "on_exit callbacks only run when the state is left"
