# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import pytest

from commands3 import (
    Command,
    Mechanism,
    Scheduler,
    Trigger,
    await_,
    park,
    yield_,
)
from commands3.binding import Binding, BindingType, ForCommand


class DummyMechanism(Mechanism):
    pass


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


async def _one_tick():
    await yield_()


def _hooked(mechanism, invocations, body=park):
    if mechanism is None:
        stage = Command.no_requirements(body)
    else:
        stage = Command.requiring(mechanism).executing(body)
    return (
        stage.when_exited(lambda: invocations.append("on_exit"))
        .when_canceled(lambda: invocations.append("on_cancel"))
        .named("Hooked")
    )


def test_on_exit_runs_on_natural_completion_but_not_on_cancel(scheduler):
    invocations = []
    command = _hooked(DummyMechanism(), invocations, body=_one_tick)

    scheduler.schedule(command)
    scheduler.run()
    scheduler.run()

    assert not scheduler.is_scheduled_or_running(command)
    assert invocations == ["on_exit"]


def test_on_exit_runs_before_on_cancel_when_canceled(scheduler):
    invocations = []
    command = _hooked(DummyMechanism(), invocations)

    scheduler.schedule(command)
    scheduler.run()
    scheduler.cancel(command)

    assert invocations == ["on_exit", "on_cancel"]


def test_on_exit_runs_before_on_cancel_on_cancel_all(scheduler):
    invocations = []
    command = _hooked(None, invocations)

    scheduler.schedule(command)
    scheduler.run()
    scheduler.cancel_all()

    assert invocations == ["on_exit", "on_cancel"]


def test_on_exit_runs_before_on_cancel_when_interrupted(scheduler):
    invocations = []
    m = DummyMechanism()
    command = _hooked(m, invocations)
    interrupter = Command.requiring(m).executing(park).named("Interrupter")

    scheduler.schedule(command)
    scheduler.run()
    scheduler.schedule(interrupter)
    scheduler.run()

    assert invocations == ["on_exit", "on_cancel"]


def test_on_exit_runs_when_parent_is_canceled(scheduler):
    invocations = []
    child = _hooked(DummyMechanism(), invocations)
    parent = Command.sequence(child).named("Seq")

    scheduler.schedule(parent)
    scheduler.run()
    scheduler.cancel(parent)

    assert invocations == ["on_exit", "on_cancel"]


def test_on_exit_does_not_run_when_canceling_a_queued_command(scheduler):
    invocations = []
    command = _hooked(DummyMechanism(), invocations)

    scheduler.schedule(command)
    scheduler.cancel(command)
    scheduler.run()

    assert invocations == []


def test_on_exit_does_not_run_on_cancel_all_for_a_queued_command(scheduler):
    invocations = []
    command = _hooked(None, invocations)

    scheduler.schedule(command)
    scheduler.cancel_all()

    assert invocations == []


def test_on_exit_does_not_run_when_interrupting_a_queued_command(scheduler):
    invocations = []
    m = DummyMechanism()
    queued = _hooked(m, invocations)
    interrupter = Command.requiring(m).executing(park).named("Interrupter")

    scheduler.schedule(queued)
    scheduler.schedule(interrupter)
    scheduler.run()

    assert invocations == []


def test_when_exited_throws_after_build():
    stage = Command.no_requirements(_one_tick)
    stage.named("cmd")

    with pytest.raises(RuntimeError, match="Command builders cannot be reused"):
        stage.when_exited(lambda: None)


def test_command_scoped_bindings_are_not_tracked_for_cleanup(scheduler):
    flag = {"value": True}
    bound = Command.no_requirements(park).named("Bound")

    async def scoping_body():
        Trigger(lambda: flag["value"], scheduler).while_true(bound)
        await park()

    scoping = Command.no_requirements(scoping_body).named("Scoping")
    scheduler.schedule(scoping)
    scheduler.run()
    scheduler.run()

    assert scheduler.is_running(bound)
    assert not any(isinstance(b.scope, ForCommand) for b in scheduler._active_bindings)


def test_rescheduling_a_command_scoped_binding_after_its_parent_exits_survives(
    scheduler,
):
    bound = Command.no_requirements(park).named("Bound")
    scoping = Command.no_requirements(park).named("Scoping")
    scheduler.schedule(scoping)
    scheduler.run()

    # Bind directly rather than through a Trigger: Trigger.unbind() has its
    # own cancel path that would mask the scheduler's binding tracking.
    scheduler._schedule_binding(
        Binding(ForCommand(scheduler, scoping), BindingType.RUN_WHILE_HIGH, bound)
    )
    scheduler.run()
    assert scheduler.is_running(bound)

    scheduler.cancel(scoping)
    assert not scheduler.is_running(bound)

    # A stale tracked binding would cancel this fresh run on the next tick.
    scheduler.schedule(bound)
    scheduler.run()

    assert scheduler.is_running(bound)


def test_compositions_with_shared_commands_do_not_self_cancel(scheduler):
    mech = DummyMechanism()
    state = {"count": 0, "canceled": 0}

    async def inner_body():
        state["count"] = 0
        while True:
            state["count"] += 1
            await yield_()

    inner = (
        Command.requiring(mech)
        .executing(inner_body)
        .when_canceled(lambda: state.__setitem__("canceled", state["canceled"] + 1))
        .named("Inner")
    )

    async def await_inner():
        await await_(inner)

    parent1 = Command.requiring(mech).executing(await_inner).named("Parent 1")
    parent2 = Command.requiring(mech).executing(await_inner).named("Parent 2")

    scheduler.schedule(parent1)
    scheduler.run()
    assert scheduler.get_running_commands() == [parent1, inner]
    scheduler.run()
    assert state["count"] == 2

    scheduler.schedule(parent2)
    scheduler.run()
    assert scheduler.get_running_commands() == [parent2, inner]
    assert state["canceled"] == 1
    assert state["count"] == 1

    scheduler.run()
    assert scheduler.get_running_commands() == [parent2, inner]
    assert state["canceled"] == 1, "inner was canceled again"
    assert state["count"] == 2


def test_compositions_awaiting_the_same_command_do_not_interrupt(scheduler):
    shared = Command.requiring(DummyMechanism()).executing(park).named("Shared")

    async def await_shared():
        await await_(shared)

    parent1 = Command.no_requirements(await_shared).named("Parent 1")
    parent2 = Command.no_requirements(await_shared).named("Parent 2")

    scheduler.schedule(parent1)
    scheduler.run()
    assert scheduler.get_running_commands() == [parent1, shared]

    scheduler.schedule(parent2)
    scheduler.run()
    assert scheduler.get_running_commands() == [parent1, shared, parent2]
