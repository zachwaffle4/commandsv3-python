# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""``SchedulerEvent`` emission: what is emitted, for whom, and in what order."""

import dataclasses

import pytest

from commands3 import (
    Command,
    LowerPriorityThanRunningCommand,
    Mechanism,
    Scheduler,
    SchedulerEvent,
    await_,
    fork,
    park,
    scheduler_event,
    yield_,
)
from commands3 import scheduler_event as se


class DummyMechanism(Mechanism):
    def __init__(self, name: str, scheduler: Scheduler) -> None:
        super().__init__(name)
        self._scheduler = scheduler

    def get_registered_scheduler(self) -> Scheduler:
        return self._scheduler


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


@pytest.fixture
def log(scheduler, watch_events):
    return watch_events(scheduler)


async def _noop_body():
    pass


async def _park_body():
    await park()


def _summary(log):
    # (event class name, command name) pairs, for comparing whole histories.
    return [(type(e).__name__, e.command.name) for e in log.events]


def test_one_shot_command_emits_scheduled_mounted_completed(scheduler, log):
    command = Command.no_requirements(_noop_body).named("OneShot")

    scheduler.schedule(command)
    scheduler.run()

    assert _summary(log) == [
        ("Scheduled", "OneShot"),
        ("Mounted", "OneShot"),
        ("Completed", "OneShot"),
    ]
    assert not scheduler.is_scheduled_or_running(command)


def test_yielding_command_emits_mounted_and_yielded_each_tick(scheduler, log):
    async def body():
        await yield_()

    command = Command.no_requirements(body).named("Yields Once")

    scheduler.schedule(command)
    scheduler.run()
    scheduler.run()

    assert _summary(log) == [
        ("Scheduled", "Yields Once"),
        ("Mounted", "Yields Once"),
        ("Yielded", "Yields Once"),
        ("Mounted", "Yields Once"),
        ("Completed", "Yields Once"),
    ]


def test_events_carry_nondecreasing_integer_timestamps(scheduler, log):
    scheduler.schedule(Command.no_requirements(_park_body).named("A"))
    scheduler.run()
    scheduler.run()

    stamps = [e.timestamp_nanos for e in log.events]
    assert len(stamps) >= 4
    assert all(isinstance(s, int) for s in stamps)
    assert stamps == sorted(stamps)


def test_events_are_frozen_dataclasses_you_can_match_on(scheduler, log):
    command = Command.no_requirements(_noop_body).named("OneShot")
    scheduler.schedule(command)
    scheduler.run()

    event = log.events[0]
    assert isinstance(event, SchedulerEvent)
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.command = command

    match event:
        case scheduler_event.Scheduled(command=c):
            assert c is command
        case _:
            pytest.fail("expected a Scheduled event")


def test_cancel_running_emits_event(scheduler, log):
    command = Command.no_requirements(_park_body).named("Command")
    scheduler.schedule(command)
    scheduler.run()

    scheduler.cancel(command)

    log.assert_canceled(command)


def test_cancel_queued_emits_event(scheduler, log):
    command = Command.no_requirements(_park_body).named("Command")
    scheduler.schedule(command)

    scheduler.cancel(command)

    log.assert_canceled(command)


def test_cancel_unknown_does_not_emit_event(scheduler, log):
    command = Command.no_requirements(_park_body).named("Command")

    scheduler.cancel(command)

    assert log.events == []


def test_cancel_all_emits_event_for_queued_and_running(scheduler, log):
    running = Command.no_requirements(_park_body).named("Running")
    queued = Command.no_requirements(_park_body).named("Queued")
    scheduler.schedule(running)
    scheduler.run()
    scheduler.schedule(queued)

    scheduler.cancel_all()

    log.assert_canceled(running)
    log.assert_canceled(queued)


def test_canceling_a_parent_emits_events_for_its_children(scheduler, log):
    child = Command.no_requirements(_park_body).named("Child")

    async def parent_body():
        await await_(child)

    parent = Command.no_requirements(parent_body).named("Parent")
    scheduler.schedule(parent)
    scheduler.run()

    scheduler.cancel(parent)

    log.assert_canceled(parent)
    log.assert_canceled(child)


def test_interrupting_a_running_command_emits_interrupted_then_canceled(scheduler, log):
    mech = DummyMechanism("Mech", scheduler)
    old = Command.requiring(mech).executing(park).named("Old")
    new = Command.requiring(mech).executing(park).named("New")

    scheduler.schedule(old)
    scheduler.run()
    log.events.clear()

    scheduler.schedule(new)
    scheduler.run()

    assert [type(e) for e in log.events[:3]] == [
        se.Scheduled,
        se.Interrupted,
        se.Canceled,
    ]
    interrupted = log.events[1]
    assert isinstance(interrupted, se.Interrupted)
    assert interrupted.command is old
    assert interrupted.interrupter is new
    log.assert_canceled(old)


def test_interrupting_a_queued_command_emits_interrupted_then_canceled(scheduler, log):
    mech = DummyMechanism("Mech", scheduler)
    old = Command.requiring(mech).executing(park).named("Old")
    new = Command.requiring(mech).executing(park).named("New")

    scheduler.schedule(old)
    scheduler.schedule(new)

    # The queued command is evicted by the one scheduled after it.
    assert _summary(log)[0] == ("Scheduled", "Old")
    assert [type(e) for e in log.events] == [
        se.Scheduled,
        se.Interrupted,
        se.Canceled,
        se.Scheduled,
    ]
    interrupted = log.events[1]
    assert isinstance(interrupted, se.Interrupted)
    assert (interrupted.command, interrupted.interrupter) == (old, new)
    scheduler.cancel_all()  # `new` was never started; don't leak its coroutine


def test_child_error_event_history(scheduler, log):
    class Boom(RuntimeError):
        pass

    async def child_body():
        await yield_()
        raise Boom("The exception")  # does not bubble up to the parent

    child = Command.no_requirements(child_body).named("Child 1")

    async def parent_body():
        await await_(child)
        await park()  # pretend other things would happen after the child

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(parent)
    scheduler.run()  # schedules the child and adds it to the running set

    with pytest.raises(Boom) as raised:  # the error surfaces in the child
        scheduler.run()

    assert not scheduler.is_running(parent)
    assert not scheduler.is_running(child)

    assert [type(e) for e in log.events] == [
        se.Scheduled,  # parent
        se.Mounted,  # parent
        se.Scheduled,  # child
        se.Mounted,  # child
        se.Yielded,  # child
        se.Yielded,  # parent
        se.Mounted,  # child, remounted
        se.CompletedWithError,  # child
        se.Canceled,  # parent
    ]
    assert [e.command for e in log.events] == [
        parent,
        parent,
        child,
        child,
        child,
        parent,
        child,
        child,
        parent,
    ]
    errored = log.events[7]
    assert isinstance(errored, se.CompletedWithError)
    assert errored.error is raised.value


def test_completed_with_error_precedes_the_childrens_canceled_events(scheduler, log):
    grandchild = Command.no_requirements(_park_body).named("Grandchild")

    async def failing_body():
        fork(grandchild)
        await yield_()
        raise RuntimeError("Bang")

    failing = Command.no_requirements(failing_body).named("Failing")
    scheduler.schedule(failing)
    scheduler.run()

    with pytest.raises(RuntimeError):
        scheduler.run()

    kinds = [(type(e), e.command) for e in log.events]
    assert kinds.index((se.CompletedWithError, failing)) < kinds.index(
        (se.Canceled, grandchild)
    )


def test_fork_failure_is_reported_once_by_the_command_that_failed(scheduler, log):
    mech = DummyMechanism("Mech", scheduler)
    high = Command.requiring(mech).executing(park).with_priority(512).named("High")
    unschedulable = Command.requiring(mech).executing(park).named("Unschedulable")

    async def current_body():
        await await_(unschedulable)

    current = Command.no_requirements(current_body).named("Current")

    async def parent_body():
        await await_(current)

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(high)
    scheduler.schedule(parent)
    scheduler.run()

    # Only the command that failed to fork reports it, not its ancestors.
    failures = log.of_type(se.ForkFailure)
    assert len(failures) == 1
    failure = failures[0]
    assert isinstance(failure, se.ForkFailure)
    assert failure.command is current
    assert len(failure.failures) == 1
    reason = failure.failures[0]
    assert isinstance(reason, LowerPriorityThanRunningCommand)
    assert reason.command is unschedulable
    assert reason.already_running is high

    # The whole composition is still canceled, the failing command included.
    for command in (parent, current):
        log.assert_canceled(command)


def test_sideload_emits_no_events(scheduler, log):
    count = 0

    def tick():
        nonlocal count
        count += 1

    scheduler.add_periodic(tick)
    scheduler.run()

    assert count == 1
    assert log.events == []


def test_forking_from_a_sideload_emits_events_for_the_forked_command(scheduler, log):
    command = Command.no_requirements(_park_body).named("Forked")

    async def body():
        fork(command)

    scheduler.sideload(body)
    scheduler.run()

    assert _summary(log) == [
        ("Scheduled", "Forked"),
        ("Mounted", "Forked"),
        ("Yielded", "Forked"),
    ]


def test_listeners_run_in_registration_order_and_dedupe(scheduler):
    order = []

    def first(event):
        order.append("first")

    def second(event):
        order.append("second")

    scheduler.add_event_listener(first)
    scheduler.add_event_listener(second)
    scheduler.add_event_listener(first)  # no additional effect

    scheduler.schedule(Command.no_requirements(_park_body).named("A"))

    # One event (Scheduled), delivered once to each listener.
    assert order == ["first", "second"]

    scheduler.cancel_all()  # never started; don't leak its coroutine


@pytest.mark.filterwarnings("ignore:coroutine .* was never awaited")
def test_listener_exception_propagates(scheduler):
    # The raise happens while scheduling, before the command is tracked, so
    # its never-started coroutine is dropped. That's expected here.
    def listener(event):
        raise ValueError("listener failed")

    scheduler.add_event_listener(listener)

    with pytest.raises(ValueError, match="listener failed"):
        scheduler.schedule(Command.no_requirements(_park_body).named("A"))
