# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Errors raised by command bodies: where they surface and what is cleaned up.
How the failing command is named on the exception is covered in
``test_scheduler.py``.
"""

import pytest

from commands3 import (
    Command,
    Mechanism,
    Scheduler,
    Trigger,
    await_,
    failing_command,
    fork,
    park,
    yield_,
)
from commands3 import scheduler_event as se


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


async def _park_body():
    await park()


def test_error_in_a_trigger_bound_command_surfaces_from_run(scheduler):
    mechanism = DummyMechanism("X", scheduler)

    async def body():
        raise RuntimeError("The exception")

    command = mechanism.run(body).named("Bad Behavior")
    Trigger(lambda: True, scheduler).on_true(command)

    with pytest.raises(RuntimeError, match="The exception") as raised:
        scheduler.run()

    assert failing_command(raised.value) is command


def test_error_in_a_nested_trigger_bound_command_surfaces_from_run(scheduler):
    async def throwing_body():
        raise IndexError("list index out of range")

    throws = Command.no_requirements(throwing_body).named("Throws IndexError")

    async def inner_body():
        Trigger(lambda: True, scheduler).on_true(throws)
        await park()

    inner = Command.no_requirements(inner_body).named("Schedules With Trigger")

    async def outer_body():
        await await_(inner)

    outer = Command.no_requirements(outer_body).named("Schedules Directly")

    scheduler.schedule(outer)

    # The first run sets up the trigger but doesn't fire it. The second run
    # fires it, which runs the inner command and raises.
    scheduler.run()

    with pytest.raises(IndexError) as raised:
        scheduler.run()

    assert failing_command(raised.value) is throws


def test_command_encountering_error_cancels_children(scheduler):
    child = Command.no_requirements(_park_body).named("Child 1")

    async def body():
        fork(child)
        raise RuntimeError("The exception")

    command = Command.no_requirements(body).named("Bad Behavior")

    scheduler.schedule(command)
    with pytest.raises(RuntimeError):
        scheduler.run()

    assert not scheduler.is_scheduled_or_running(command), (
        "the command should have been removed from the scheduler"
    )
    assert not scheduler.is_scheduled_or_running(child), (
        "the child should have been removed from the scheduler"
    )


def test_child_command_encountering_error_cancels_parent(scheduler):
    async def child_body():
        raise RuntimeError("The exception")  # bubbles up to the parent

    child = Command.no_requirements(child_body).named("Child 1")

    async def parent_body():
        await await_(child)
        await park()  # pretend other things would happen after the child

    command = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(command)
    # The child's own error must surface, not something raised while tearing
    # the parent down.
    with pytest.raises(RuntimeError, match="The exception") as raised:
        scheduler.run()

    assert failing_command(raised.value) is child
    assert not scheduler.is_running(command), (
        "the parent should have been removed from the scheduler"
    )
    assert not scheduler.is_running(child), (
        "the child should have been removed from the scheduler"
    )


def test_a_parent_torn_down_by_its_childs_error_is_canceled(scheduler, watch_events):
    log = watch_events(scheduler)
    hooks = []

    async def child_body():
        raise RuntimeError("The exception")

    child = Command.no_requirements(child_body).named("Child")

    async def parent_body():
        try:
            await await_(child)
        finally:
            hooks.append("finally")

    parent = (
        Command.no_requirements(parent_body)
        .when_exited(lambda: hooks.append("on_exit"))
        .when_canceled(lambda: hooks.append("on_cancel"))
        .named("Parent")
    )

    scheduler.schedule(parent)
    with pytest.raises(RuntimeError):
        scheduler.run()

    # The parent is canceled rather than reported as having failed: it didn't
    # raise anything itself.
    assert hooks == ["finally", "on_exit", "on_cancel"]
    log.assert_canceled(parent)
    assert [e.command for e in log.of_type(se.CompletedWithError)] == [child]


def test_error_cancels_every_ancestor_up_to_the_root(scheduler, watch_events):
    log = watch_events(scheduler)

    async def child_body():
        raise RuntimeError("The exception")

    child = Command.no_requirements(child_body).named("Child")

    async def middle_body():
        await await_(child)

    middle = Command.no_requirements(middle_body).named("Middle")

    async def root_body():
        await await_(middle)

    root = Command.no_requirements(root_body).named("Root")

    scheduler.schedule(root)
    with pytest.raises(RuntimeError, match="The exception") as raised:
        scheduler.run()

    assert failing_command(raised.value) is child
    for command in (root, middle, child):
        assert not scheduler.is_scheduled_or_running(command), command.name
    log.assert_canceled(middle)
    log.assert_canceled(root)


def test_error_in_a_child_cancels_its_siblings(scheduler):
    sibling = Command.no_requirements(_park_body).named("Sibling")

    async def child_body():
        raise RuntimeError("The exception")

    child = Command.no_requirements(child_body).named("Child")

    async def parent_body():
        fork(sibling)
        await await_(child)

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(parent)
    with pytest.raises(RuntimeError, match="The exception"):
        scheduler.run()

    assert not scheduler.is_scheduled_or_running(sibling)
    assert not scheduler.is_scheduled_or_running(parent)


def test_a_parent_that_handles_its_childs_error_keeps_running(scheduler):
    caught = []

    async def child_body():
        raise RuntimeError("The exception")

    child = Command.no_requirements(child_body).named("Child")

    async def parent_body():
        try:
            await await_(child)
        except RuntimeError as e:
            caught.append(str(e))
        await park()

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(parent)
    scheduler.run()

    assert caught == ["The exception"]
    assert scheduler.is_running(parent)
    assert not scheduler.is_running(child)


def test_error_in_a_child_that_fails_on_a_later_tick_cancels_the_parent(
    scheduler, watch_events
):
    # Unlike the awaited-child cases above, nothing is mounted when this child
    # raises: the scheduler steps it directly, on its own turn.
    log = watch_events(scheduler)
    hooks = []
    tick = {"count": 0}

    async def child_body():
        await yield_()
        tick["count"] += 1
        raise RuntimeError("The exception")

    child = Command.no_requirements(child_body).named("Child")

    async def parent_body():
        await await_(child)

    parent = (
        Command.no_requirements(parent_body)
        .when_canceled(lambda: hooks.append("on_cancel"))
        .named("Parent")
    )

    scheduler.schedule(parent)
    scheduler.run()
    assert scheduler.is_running(parent)
    assert scheduler.is_running(child)

    with pytest.raises(RuntimeError, match="The exception") as raised:
        scheduler.run()

    assert failing_command(raised.value) is child
    assert hooks == ["on_cancel"]
    log.assert_canceled(parent)
    assert not scheduler.is_scheduled_or_running(parent)
    assert not scheduler.is_scheduled_or_running(child)
