# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Priority inheritance and fork-failure behavior, ported from Java's
``SchedulerPriorityLevelTests``.

The basic "higher priority evicts, lower priority is rejected" cases live in
``test_scheduler.py``; this file covers what #9207 added - a command's
*effective* priority being the highest in its scheduling hierarchy, and
fork/await becoming all-or-nothing.

Assertions on ``SchedulerEvent`` in the Java originals are omitted until the
event listener mechanism is ported (see ``PORTING_PLAN.md`` phase 6).
"""

import pytest

from commands3 import (
    DEFAULT_PRIORITY,
    Command,
    ForkFailed,
    LowerPriorityThanRunningCommand,
    Mechanism,
    Scheduler,
    Trigger,
    all_of,
    any_of,
    await_,
    fork,
    park,
)


class DummyMechanism(Mechanism):
    """
    Like Java's ``DummyMechanism`` test helper, this can be pointed at a
    specific scheduler. ``Mechanism.get_registered_scheduler()`` otherwise
    returns the shared default instance, so ``set_default_command()`` on a
    plain mechanism would bypass a test's isolated scheduler entirely.
    """

    def __init__(
        self, name: str | None = None, scheduler: Scheduler | None = None
    ) -> None:
        super().__init__(name)
        self._scheduler = scheduler

    def get_registered_scheduler(self) -> Scheduler:
        if self._scheduler is None:
            return super().get_registered_scheduler()
        return self._scheduler


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


def _priority_command(priority: int, mechanism: Mechanism, name: str) -> Command:
    """A command that claims ``mechanism`` at ``priority`` and parks."""
    return (
        Command.requiring(mechanism).executing(park).with_priority(priority).named(name)
    )


# -- Fork operations, parameterized the way Java parameterizes them ---------
#
# Wrapped as async adapters with one uniform signature so the same test body
# can drive fork (synchronous, variadic), await_ (single command), and
# all_of/any_of (a collection).


async def _fork_op(commands, *, cancel_on_failure=True):
    return fork(*commands, cancel_on_failure=cancel_on_failure)


async def _await_op(commands, *, cancel_on_failure=True):
    return await await_(commands[0], cancel_on_failure=cancel_on_failure)


async def _all_of_op(commands, *, cancel_on_failure=True):
    return await all_of(commands, cancel_on_failure=cancel_on_failure)


async def _any_of_op(commands, *, cancel_on_failure=True):
    return await any_of(commands, cancel_on_failure=cancel_on_failure)


single_child_ops = pytest.mark.parametrize(
    "operation",
    [
        pytest.param(_fork_op, id="fork"),
        pytest.param(_await_op, id="await_"),
        pytest.param(_all_of_op, id="all_of"),
        pytest.param(_any_of_op, id="any_of"),
    ],
)

multi_child_ops = pytest.mark.parametrize(
    "operation",
    [
        pytest.param(_fork_op, id="fork"),
        pytest.param(_all_of_op, id="all_of"),
        pytest.param(_any_of_op, id="any_of"),
    ],
)


# -- Priority inheritance --------------------------------------------------


def test_child_inherits_higher_parent_priority(scheduler):
    mechanism = DummyMechanism()

    higher_priority = _priority_command(200, mechanism, "Higher")
    low_priority_child = _priority_command(-1000, mechanism, "Child")

    async def parent_body():
        await await_(low_priority_child)

    parent = Command.no_requirements(parent_body).with_priority(1000).named("Parent")

    scheduler.schedule(higher_priority)
    scheduler.schedule(parent)
    scheduler.run()

    assert scheduler.is_running(parent)
    assert scheduler.is_running(low_priority_child)
    assert not scheduler.is_running(higher_priority), (
        "the 200-priority command should have been interrupted by a child "
        "inheriting its parent's priority of 1000"
    )


def test_inner_default_command_inherits_higher_parent_priority(scheduler):
    mechanism = DummyMechanism(scheduler=scheduler)

    higher_priority = _priority_command(200, mechanism, "Higher")
    low_priority_child = _priority_command(-1000, mechanism, "Default")

    async def parent_body():
        mechanism.set_default_command(low_priority_child)
        await park()

    parent = Command.no_requirements(parent_body).with_priority(1000).named("Parent")

    scheduler.schedule(parent)
    scheduler.run()
    assert scheduler.get_running_commands() == [parent, low_priority_child]

    result = scheduler.schedule(higher_priority)

    assert result == LowerPriorityThanRunningCommand(
        higher_priority, low_priority_child
    )
    assert scheduler.get_running_commands() == [parent, low_priority_child], (
        "the parent and its inner default command should keep running"
    )


def test_inner_trigger_command_inherits_higher_parent_priority(scheduler):
    mechanism = DummyMechanism()

    higher_priority = _priority_command(200, mechanism, "Higher")
    low_priority_child = _priority_command(-1000, mechanism, "Child")

    trigger = Trigger(lambda: True, scheduler)

    async def parent_body():
        # The trigger is created outside this command and before it's
        # scheduled, so an on_true/while_true binding wouldn't fire - the
        # signal edge happens before the binding can be evaluated.
        trigger.retry_while_true(low_priority_child)
        await park()

    parent = Command.no_requirements(parent_body).with_priority(1000).named("Parent")

    scheduler.schedule(higher_priority)
    scheduler.run()

    scheduler.schedule(parent)
    scheduler.run()  # schedules the parent, which adds the binding
    scheduler.run()  # polls the binding, which schedules the child

    assert scheduler.get_running_commands() == [parent, low_priority_child], (
        "a trigger-bound child should inherit its parent's priority"
    )


def test_conflicting_children_lower_priority_parent_loses(scheduler):
    mechanism = DummyMechanism()

    child1 = _priority_command(0, mechanism, "Child1")
    child2 = _priority_command(0, mechanism, "Child2")

    async def parent1_body():
        await await_(child1)

    async def parent2_body():
        # child2 inherits parent2's priority of 1000, so it loses to child1
        # at an inherited 2000.
        await await_(child2, cancel_on_failure=False)

    parent1 = Command.no_requirements(parent1_body).with_priority(2000).named("Parent1")
    parent2 = Command.no_requirements(parent2_body).with_priority(1000).named("Parent2")

    scheduler.schedule(parent1)
    scheduler.schedule(parent2)
    scheduler.run()

    assert scheduler.get_running_commands() == [parent1, child1]


def test_conflicting_children_higher_priority_parent_wins(scheduler):
    mechanism = DummyMechanism()

    child1 = _priority_command(0, mechanism, "Child1")
    child2 = _priority_command(0, mechanism, "Child2")

    async def parent1_body():
        await await_(child1)

    async def parent2_body():
        # child2 inherits parent2's priority of 2000, so it beats child1 at
        # an inherited 1000.
        await await_(child2)

    parent1 = Command.no_requirements(parent1_body).with_priority(1000).named("Parent1")
    parent2 = Command.no_requirements(parent2_body).with_priority(2000).named("Parent2")

    scheduler.schedule(parent1)
    scheduler.schedule(parent2)
    scheduler.run()

    assert scheduler.get_running_commands() == [parent2, child2]


# -- Fork failure ----------------------------------------------------------


@single_child_ops
def test_unschedulable_child_cancels_parent(scheduler, operation):
    mechanism = DummyMechanism()

    high_priority = _priority_command(512, mechanism, "High")
    default_priority = _priority_command(DEFAULT_PRIORITY, mechanism, "Default")

    async def parent_body():
        await operation([default_priority])

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(high_priority)
    scheduler.schedule(parent)
    scheduler.run()

    assert not scheduler.is_running(parent), "the parent should have been canceled"
    assert scheduler.is_running(high_priority)
    assert not scheduler.is_scheduled_or_running(default_priority)


@single_child_ops
def test_unschedulable_child_gives_failure_result(scheduler, operation):
    mechanism = DummyMechanism()

    high_priority = _priority_command(512, mechanism, "High")
    default_priority = _priority_command(DEFAULT_PRIORITY, mechanism, "Default")

    _assert_fork_failure(
        scheduler,
        operation,
        already_running=high_priority,
        commands=[default_priority],
        expected_failures=[default_priority],
    )


@multi_child_ops
def test_unschedulable_child_with_schedulable_sibling_gives_failure_result(
    scheduler, operation
):
    busy = DummyMechanism("Busy")
    idle = DummyMechanism("Idle")

    high_priority = _priority_command(512, busy, "High")
    unschedulable = _priority_command(DEFAULT_PRIORITY, busy, "Unschedulable")
    schedulable = _priority_command(DEFAULT_PRIORITY, idle, "Schedulable")

    _assert_fork_failure(
        scheduler,
        operation,
        already_running=high_priority,
        commands=[unschedulable, schedulable],
        expected_failures=[unschedulable],
    )


def _assert_fork_failure(
    scheduler, operation, *, already_running, commands, expected_failures
):
    async def parent_body():
        result = await operation(commands, cancel_on_failure=False)

        assert result.failed
        assert [
            failure.command for failure in result.failed_commands
        ] == expected_failures
        assert not any(failure.successful for failure in result.failed_commands)

        await park()

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(already_running)
    scheduler.schedule(parent)
    scheduler.run()

    assert scheduler.is_running(parent), "the parent should still be running"
    assert scheduler.is_running(already_running)
    for command in commands:
        assert not scheduler.is_scheduled_or_running(command), (
            f"{command.name} should not have been scheduled - forking is all-or-nothing"
        )


@single_child_ops
def test_unschedulable_child_cancels_entire_composition(scheduler, operation):
    mechanism = DummyMechanism()

    high_priority = _priority_command(512, mechanism, "High")
    unschedulable = _priority_command(DEFAULT_PRIORITY, mechanism, "Unschedulable")

    grandchild = Command.no_requirements(park).named("Grandchild")

    async def child_body():
        fork(grandchild)
        await park()

    child = Command.no_requirements(child_body).named("Child")

    async def current_body():
        fork(child)
        await operation([unschedulable])

    current = Command.no_requirements(current_body).named("Current")

    async def parent_body():
        await await_(current)

    parent = Command.no_requirements(parent_body).named("Parent")

    async def grandparent_body():
        await await_(parent)

    grandparent = Command.no_requirements(grandparent_body).named("Grandparent")

    scheduler.schedule(high_priority)
    scheduler.schedule(grandparent)
    scheduler.run()

    assert scheduler.is_running(high_priority), (
        "the higher priority command should still be running"
    )
    for command in (grandparent, parent, current, child, grandchild):
        assert not scheduler.is_scheduled_or_running(command), (
            f"{command.name} should have been canceled"
        )


@multi_child_ops
def test_high_priority_grandchild_blocks_low_priority_sibling(scheduler, operation):
    """
    child1 and child2 are both forkable up front - no shared requirements
    with anything running - but child1 immediately awaits a higher-priority
    grandchild that requires the same mechanism as child2, which no up-front
    check can predict.
    """
    mechanism = DummyMechanism()

    grandchild = _priority_command(1000, mechanism, "Grandchild")
    child2 = _priority_command(0, mechanism, "Child2")

    async def child1_body():
        await await_(grandchild)

    child1 = Command.no_requirements(child1_body).named("Child1")

    observed = {}

    async def parent_body():
        observed["result"] = await operation([child1, child2], cancel_on_failure=False)

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(parent)
    scheduler.run()

    result = observed["result"]
    assert result.failed
    assert result.partial_success
    assert result.failed_commands == (
        LowerPriorityThanRunningCommand(child2, grandchild),
    )
    assert result.forked_commands == (child1,)


def test_fork_failure_raises_fork_failed_outside_a_composition(scheduler):
    """
    ``ForkFailed`` is a ``CommandCancelled`` subclass, so it stops the
    command rather than escaping ``run()`` to the caller.
    """
    mechanism = DummyMechanism()

    high_priority = _priority_command(512, mechanism, "High")
    unschedulable = _priority_command(DEFAULT_PRIORITY, mechanism, "Unschedulable")

    raised = []

    async def parent_body():
        try:
            fork(unschedulable)
        except ForkFailed as e:
            raised.append(e)
            raise

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(high_priority)
    scheduler.schedule(parent)
    scheduler.run()

    assert len(raised) == 1
    assert raised[0].result.failed_commands == (
        LowerPriorityThanRunningCommand(unschedulable, high_priority),
    )
    assert not scheduler.is_running(parent)


def test_fork_cleanup_runs_on_fork_failure(scheduler):
    """
    Because fork failure unwinds the command as a cancellation rather than
    abandoning its frames, ``try/finally`` cleanup still runs - consistent
    with DIVERGENCES.md #1.
    """
    mechanism = DummyMechanism()

    high_priority = _priority_command(512, mechanism, "High")
    unschedulable = _priority_command(DEFAULT_PRIORITY, mechanism, "Unschedulable")

    cleaned_up = []

    async def parent_body():
        try:
            fork(unschedulable)
        finally:
            cleaned_up.append(True)

    parent = Command.no_requirements(parent_body).named("Parent")

    scheduler.schedule(high_priority)
    scheduler.schedule(parent)
    scheduler.run()

    assert cleaned_up == [True]
