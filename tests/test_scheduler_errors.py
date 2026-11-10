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
)


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


@pytest.mark.xfail(
    strict=True,
    raises=ValueError,
    reason=(
        "Known bug (PORTING_PLAN.md, 'Deferred'): when a child started inside "
        "its parent's run raises, _handle_command_exception() cancels the "
        "still-mounted parent, and cancel() raises ValueError, masking the "
        "child's real exception. Java surfaces the original error."
    ),
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
    with pytest.raises(RuntimeError):
        scheduler.run()

    assert not scheduler.is_running(command), (
        "the parent should have been removed from the scheduler"
    )
    assert not scheduler.is_running(child), (
        "the child should have been removed from the scheduler"
    )
