# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
What a canceled command's cleanup - its ``finally`` blocks, or code after
catching ``CommandCancelled`` - may do, and what happens when it breaks the
rules.

Cleanup is synchronous. It runs as if no command were executing: whatever it
schedules is queued as a top-level command, and ``fork()``/``await_()`` and
friends raise. Cleanup that suspends, or raises, doesn't stop the
cancellation: the command is still canceled, its hooks run and its children
are canceled, and the error is raised afterward.
"""

import random

import pytest

from commands3 import (
    Command,
    CommandCancelled,
    Mechanism,
    Scheduler,
    fork,
    park,
    scheduler_event,
    yield_,
)


class DummyMechanism(Mechanism):
    pass


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


def _command(body, name="Command", hooks=None, requires=()):
    builder = Command.requiring(*requires) if requires else None
    stage = (
        builder.executing(body)
        if builder is not None
        else Command.no_requirements(body)
    )
    if hooks is not None:
        stage = stage.when_exited(lambda: hooks.append("on_exit")).when_canceled(
            lambda: hooks.append("on_cancel")
        )
    return stage.named(name)


def test_finally_runs_once_when_canceled(scheduler):
    cleanups = []

    async def body():
        try:
            await park()
        finally:
            cleanups.append("finally")

    command = _command(body)
    scheduler.schedule(command)
    scheduler.run()

    scheduler.cancel(command)
    scheduler.cancel(command)
    scheduler.run()

    assert cleanups == ["finally"]


def test_cleanup_that_suspends_is_closed_and_reported(scheduler, watch_events):
    log = watch_events(scheduler)
    hooks = []
    steps = []

    async def body():
        try:
            await park()
        finally:
            steps.append("cleanup started")
            try:
                await yield_()
                steps.append("after the suspension")
            finally:
                steps.append("closed")

    command = _command(body, hooks=hooks)
    scheduler.schedule(command)
    scheduler.run()

    with pytest.raises(RuntimeError, match="suspended while being canceled"):
        scheduler.cancel(command)

    # Closed right away rather than left suspended for the garbage collector,
    # and the cancellation itself went through.
    assert steps == ["cleanup started", "closed"]
    assert not scheduler.is_running(command)
    assert hooks == ["on_exit", "on_cancel"]
    log.assert_canceled(command)

    scheduler.run()
    assert steps == ["cleanup started", "closed"]


def test_cleanup_that_swallows_cancellation_and_keeps_going_is_closed(scheduler):
    resumed = []

    async def body():
        try:
            await park()
        except CommandCancelled:
            while True:
                await yield_()
                resumed.append(True)

    command = _command(body)
    scheduler.schedule(command)
    scheduler.run()

    with pytest.raises(RuntimeError, match="suspended while being canceled"):
        scheduler.cancel(command)

    for _ in range(3):
        scheduler.run()
    assert resumed == []
    assert not scheduler.is_running(command)


def test_async_generator_cleanup_that_suspends_is_closed_and_reported(scheduler):
    steps = []

    async def body():
        try:
            while True:
                yield
        finally:
            steps.append("cleanup started")
            yield
            steps.append("after the suspension")

    command = _command(body)
    scheduler.schedule(command)
    scheduler.run()

    with pytest.raises(RuntimeError, match="suspended while being canceled"):
        scheduler.cancel(command)

    scheduler.run()
    assert steps == ["cleanup started"]
    assert not scheduler.is_running(command)


def test_suspending_cleanup_during_cancel_all_cancels_everything(scheduler):
    async def stubborn_body():
        try:
            await park()
        finally:
            await yield_()

    stubborn = _command(stubborn_body, "Stubborn")
    other = _command(lambda: park(), "Other")
    scheduler.schedule(stubborn)
    scheduler.schedule(other)
    scheduler.run()

    with pytest.raises(RuntimeError, match="suspended while being canceled"):
        scheduler.cancel_all()

    assert scheduler.get_running_commands() == []


# -- The context cleanup runs in --------------------------------------------


def test_cleanup_schedules_a_top_level_command_not_a_child_of_the_canceler(
    scheduler,
):
    stow = _command(lambda: park(), "Stow")

    async def victim_body():
        try:
            await park()
        finally:
            scheduler.schedule(stow)

    victim = _command(victim_body, "Victim")

    async def canceler_body():
        await yield_()
        scheduler.cancel(victim)
        # Completes right away. Were Stow its child, it would go with it.

    canceler = _command(canceler_body, "Canceler")
    scheduler.schedule(victim)
    scheduler.schedule(canceler)
    scheduler.run()

    scheduler.run()  # the canceler cancels the victim and completes
    assert not scheduler.is_running(canceler)
    assert scheduler.is_scheduled(stow)

    scheduler.run()
    assert scheduler.is_running(stow)
    assert scheduler.get_parent_of(stow) is None


def test_cleanup_of_a_child_canceled_with_its_parent_schedules_a_top_level_command(
    scheduler,
):
    stow = _command(lambda: park(), "Stow")

    async def child_body():
        try:
            await park()
        finally:
            scheduler.schedule(stow)

    child = _command(child_body, "Child")

    async def parent_body():
        fork(child)
        await yield_()
        # Completing cancels the child.

    parent = _command(parent_body, "Parent")
    scheduler.schedule(parent)
    scheduler.run()
    scheduler.run()

    assert not scheduler.is_running(parent)
    assert not scheduler.is_running(child)
    scheduler.run()
    assert scheduler.is_running(stow)
    assert scheduler.get_parent_of(stow) is None


def test_command_scheduled_by_cleanup_during_promotion_evicts_its_conflicts(
    scheduler,
):
    arm, intake = DummyMechanism("Arm"), DummyMechanism("Intake")
    idle_arm = _command(lambda: park(), "IdleArm", requires=(arm,))
    stow = (
        Command.requiring(arm).executing(lambda: park()).with_priority(5).named("Stow")
    )

    async def victim_body():
        try:
            await park()
        finally:
            scheduler.schedule(stow)

    victim = _command(victim_body, "Victim", requires=(intake,))
    interrupter = (
        Command.requiring(intake)
        .executing(lambda: park())
        .with_priority(10)
        .named("Interrupter")
    )
    scheduler.schedule(idle_arm)
    scheduler.schedule(victim)
    scheduler.run()

    # Promoting the interrupter evicts the victim, whose cleanup queues Stow.
    scheduler.schedule(interrupter)
    scheduler.run()

    assert scheduler.get_running_commands_for(arm) == [stow]
    assert scheduler.get_running_commands_for(intake) == [interrupter]


def test_fork_in_cleanup_is_rejected_and_reported_after_the_tick(scheduler):
    forked = _command(lambda: park(), "Forked")

    async def victim_body():
        try:
            await park()
        finally:
            fork(forked)

    victim = _command(victim_body, "Victim")

    async def canceler_body():
        await yield_()
        scheduler.cancel(victim)
        await park()

    canceler = _command(canceler_body, "Canceler")
    scheduler.schedule(victim)
    scheduler.schedule(canceler)
    scheduler.run()

    with pytest.raises(RuntimeError, match="can't be used"):
        scheduler.run()

    # The canceler wasn't taken down by somebody else's cleanup error.
    assert scheduler.is_running(canceler)
    assert not scheduler.is_running(victim)
    assert not scheduler.is_scheduled_or_running(forked)

    scheduler.run()
    assert scheduler.is_running(canceler)


def test_cleanup_cannot_cancel_the_command_that_is_canceling_it(scheduler):
    async def victim_body():
        try:
            await park()
        finally:
            scheduler.cancel(canceler)

    victim = _command(victim_body, "Victim")
    steps = []

    async def canceler_body():
        await yield_()
        scheduler.cancel(victim)
        steps.append("cancel returned")
        await park()

    canceler = _command(canceler_body, "Canceler")
    scheduler.schedule(victim)
    scheduler.schedule(canceler)
    scheduler.run()

    with pytest.raises(RuntimeError, match="executing"):
        scheduler.run()

    assert steps == ["cancel returned"]
    assert scheduler.is_running(canceler)
    assert not scheduler.is_running(victim)


# -- Running cleanup exactly once ------------------------------------------


def test_cleanup_that_cancels_its_own_command_runs_once(scheduler):
    cleanups = []

    async def body():
        try:
            await park()
        finally:
            cleanups.append("finally")
            scheduler.cancel(command)

    command = _command(body)
    scheduler.schedule(command)
    scheduler.run()
    scheduler.cancel(command)

    assert cleanups == ["finally"]


def test_canceling_a_parent_cleans_up_each_descendant_once(scheduler, watch_events):
    log = watch_events(scheduler)
    cleanups = []

    def tracked(name, *children):
        async def body():
            try:
                if children:
                    fork(*children)
                await park()
            finally:
                cleanups.append(name)

        return _command(body, name)

    grandchild = tracked("Grandchild")
    child = tracked("Child", grandchild)
    sibling = tracked("Sibling")
    parent = tracked("Parent", child, sibling)

    scheduler.schedule(parent)
    scheduler.run()
    assert scheduler.is_running(grandchild)

    scheduler.cancel(parent)
    scheduler.cancel(parent)
    scheduler.cancel(child)
    scheduler.run()

    assert sorted(cleanups) == ["Child", "Grandchild", "Parent", "Sibling"]
    canceled = [e.command for e in log.of_type(scheduler_event.Canceled)]
    assert sorted(c.name for c in canceled) == sorted(cleanups)
    assert scheduler.get_running_commands() == []


# -- Errors during cleanup --------------------------------------------------


def test_error_in_cleanup_still_finishes_the_cancellation(scheduler, watch_events):
    log = watch_events(scheduler)
    hooks = []
    child = _command(lambda: park(), "Child")

    async def body():
        fork(child)
        try:
            await park()
        finally:
            raise ValueError("cleanup failed")

    command = _command(body, hooks=hooks)
    scheduler.schedule(command)
    scheduler.run()

    with pytest.raises(ValueError, match="cleanup failed") as info:
        scheduler.cancel(command)

    assert info.value.__traceback__ is not None
    assert hooks == ["on_exit", "on_cancel"]
    assert not scheduler.is_running(command)
    assert not scheduler.is_running(child)
    log.assert_canceled(command)
    log.assert_canceled(child)

    # The scheduler is still usable, and so is the command.
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.is_running(command)
    assert scheduler.is_running(child)
    with pytest.raises(ValueError, match="cleanup failed"):
        scheduler.cancel(command)


def test_error_in_cleanup_of_an_interrupted_command_does_not_block_the_interrupter(
    scheduler,
):
    mechanism = DummyMechanism()

    async def victim_body():
        try:
            await park()
        finally:
            raise ValueError("cleanup failed")

    victim = _command(victim_body, "Victim", requires=(mechanism,))
    interrupter = (
        Command.requiring(mechanism)
        .executing(lambda: park())
        .with_priority(10)
        .named("Interrupter")
    )
    scheduler.schedule(victim)
    scheduler.run()

    scheduler.schedule(interrupter)
    with pytest.raises(ValueError, match="cleanup failed"):
        scheduler.run()

    assert not scheduler.is_running(victim)
    assert scheduler.is_running(interrupter)


def test_error_in_an_on_cancel_hook_still_cancels_children(scheduler):
    child = _command(lambda: park(), "Child")

    async def body():
        fork(child)
        await park()

    def on_cancel():
        raise ValueError("hook failed")

    command = Command.no_requirements(body).when_canceled(on_cancel).named("Command")
    scheduler.schedule(command)
    scheduler.run()

    with pytest.raises(ValueError, match="hook failed"):
        scheduler.cancel(command)

    assert scheduler.get_running_commands() == []


def test_errors_in_several_cleanups_are_all_reported(scheduler):
    def failing(name):
        async def body():
            try:
                await park()
            finally:
                raise ValueError(name)

        return _command(body, name)

    a, b = failing("A"), failing("B")
    scheduler.schedule(a)
    scheduler.schedule(b)
    scheduler.run()

    with pytest.raises(ExceptionGroup) as info:
        scheduler.cancel_all()

    assert sorted(str(e) for e in info.value.exceptions) == ["A", "B"]
    assert scheduler.get_running_commands() == []


def test_error_in_a_command_body_does_not_run_on_exit_but_runs_finally(scheduler):
    # on_exit is for exits the scheduler drives; a body that raises skips it.
    # `finally` runs on every path, so that's where must-run cleanup goes.
    hooks = []

    async def body():
        try:
            await yield_()
            raise ValueError("body failed")
        finally:
            hooks.append("finally")

    command = _command(body, hooks=hooks)
    scheduler.schedule(command)
    scheduler.run()
    with pytest.raises(ValueError, match="body failed"):
        scheduler.run()

    assert hooks == ["finally"]
    assert not scheduler.is_running(command)


# -- Stress -----------------------------------------------------------------


@pytest.mark.parametrize("seed", range(10))
def test_random_schedule_cancel_reschedule_keeps_runs_balanced(scheduler, seed):
    rng = random.Random(seed)
    starts = {}
    cleanups = {}

    def make(name):
        async def body():
            starts[name] = starts.get(name, 0) + 1
            try:
                for _ in range(rng.randint(0, 3)):
                    await yield_()
                    # Commands mess with each other while they run.
                    target = rng.choice(commands)
                    action = rng.random()
                    if action < 0.3:
                        scheduler.cancel(target)
                    elif action < 0.6:
                        scheduler.cancel(target)
                        scheduler.schedule(target)
                    elif action < 0.7:
                        fork(rng.choice(commands), cancel_on_failure=False)
            finally:
                cleanups[name] = cleanups.get(name, 0) + 1

        return Command.no_requirements(body).named(name)

    commands = [make(f"C{i}") for i in range(8)]

    for _ in range(500):
        for command in rng.sample(commands, 3):
            scheduler.schedule(command)
        if rng.random() < 0.1:
            scheduler.cancel(rng.choice(commands))
        scheduler.run()

        for command in commands:
            # Every started run is either the one running now or has been
            # cleaned up, exactly once.
            name = command.name
            open_runs = starts.get(name, 0) - cleanups.get(name, 0)
            assert open_runs == (1 if scheduler.is_running(command) else 0), name

    scheduler.cancel_all()
    assert starts == cleanups
