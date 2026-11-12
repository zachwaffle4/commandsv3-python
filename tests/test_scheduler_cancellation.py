# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Cancellation, interruption, and ``cancel_all()``, including which hooks run
when. The ``on_exit`` ordering cases live in ``test_scheduler_on_exit.py``.
"""

import pytest

from commands3 import Command, Mechanism, Scheduler, await_, fork, park, yield_


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


async def _one_tick():
    await yield_()


async def _park_body():
    await park()


# -- Interruption and eviction ---------------------------------------------


def test_cancel_on_interrupt_does_not_resume(scheduler):
    count = 0
    mechanism = DummyMechanism("mechanism", scheduler)

    async def interrupter_body():
        pass

    async def canceled_body():
        nonlocal count
        count = 1
        await yield_()
        count = 2

    interrupter = (
        Command.requiring(mechanism)
        .executing(interrupter_body)
        .with_priority(2)
        .named("Interrupter")
    )
    canceled = (
        Command.requiring(mechanism)
        .executing(canceled_body)
        .with_priority(1)
        .named("Cancel By Default")
    )

    scheduler.schedule(canceled)
    scheduler.run()

    scheduler.schedule(interrupter)
    scheduler.run()
    assert count == 1, "the second assignment should not have run"


def test_default_command_resumes_after_interruption(scheduler):
    count = 0
    mechanism = DummyMechanism("mechanism", scheduler)

    async def default_body():
        nonlocal count
        while True:
            count += 1
            await yield_()

    async def newer_body():
        pass

    default = mechanism.run(default_body).with_priority(-1).named("Default Command")
    newer = mechanism.run(newer_body).named("Newer Command")

    mechanism.set_default_command(default)
    scheduler.run()
    assert scheduler.is_running(default), "the default command should be running"

    scheduler.schedule(newer)
    scheduler.run()
    assert not scheduler.is_running(default), "the default should have been interrupted"
    assert count == 1, "the default command should have run once"

    scheduler.run()
    assert scheduler.is_running(default), "the default command should have resumed"
    assert count == 2


def test_cancel_evicts_on_deck(scheduler):
    command = Command.no_requirements(_park_body).named("Command")
    scheduler.schedule(command)
    scheduler.cancel(command)
    assert not scheduler.is_scheduled_or_running(command)


def test_cancel_all_evicts_on_deck(scheduler):
    command = Command.no_requirements(_park_body).named("Command")
    scheduler.schedule(command)
    scheduler.cancel_all()
    assert not scheduler.is_scheduled_or_running(command)


def test_cancel_all_cancels_all(scheduler):
    commands = [
        Command.no_requirements(_one_tick).named(f"Command {i}") for i in range(1, 11)
    ]
    for command in commands:
        scheduler.schedule(command)
    scheduler.run()
    scheduler.cancel_all()
    for command in commands:
        assert not scheduler.is_running(command), (
            f"{command.name} was not canceled by cancel_all()"
        )


def test_cancel_all_starts_defaults(scheduler):
    mechanisms = []
    for i in range(1, 11):
        mechanism = DummyMechanism(f"System {i}", scheduler)
        mechanism.set_default_command(mechanism.idle())
        mechanisms.append(mechanism)

    command = (
        Command.requiring(mechanisms[0], *mechanisms[1:])
        .executing(_one_tick)
        .named("Big Command")
    )

    # Scheduling the command should evict the on-deck default commands.
    scheduler.schedule(command)

    # Running then gets it into the set of running commands.
    scheduler.run()
    assert scheduler.is_running(command)
    for mechanism in mechanisms:
        assert scheduler.get_running_commands_for(mechanism) == [command]

    # Canceling should clear out the set of running commands.
    scheduler.cancel_all()
    assert not scheduler.is_running(command), "cancel_all() did not cancel the command"

    # Ticking once schedules the defaults.
    scheduler.run()
    assert not scheduler.is_running(command)

    for mechanism in mechanisms:
        running = scheduler.get_running_commands_for(mechanism)
        assert len(running) == 1, f"{mechanism.name} should have one running command"
        assert running[0] is mechanism.get_default_command(), (
            f"{mechanism.name} is not running its default command"
        )


# -- Compositions ----------------------------------------------------------


def test_cancel_deeply_nested_compositions(scheduler):
    park_command = Command.no_requirements(_park_body).named("Park")

    async def c3_body():
        await await_(park_command)

    c3 = Command.no_requirements(c3_body).named("C3")

    async def c2_body():
        await await_(c3)

    c2 = Command.no_requirements(c2_body).named("C2")

    async def root_body():
        await await_(c2)

    root = Command.no_requirements(root_body).named("Root")

    scheduler.schedule(root)
    scheduler.run()
    assert len(scheduler.get_running_commands()) == 4

    scheduler.cancel(root)
    assert len(scheduler.get_running_commands()) == 0


def test_compositions_do_not_self_cancel(scheduler):
    mech = DummyMechanism("The mechanism", scheduler)

    park_command = mech.run(park).named("Park")

    async def c3_body():
        await await_(park_command)

    c3 = mech.run(c3_body).named("C3")

    async def c2_body():
        await await_(c3)

    c2 = mech.run(c2_body).named("C2")

    async def group_body():
        await await_(c2)

    group = mech.run(group_body).named("Group")

    scheduler.schedule(group)
    scheduler.run()
    assert len(scheduler.get_running_commands()) == 4
    assert scheduler.is_running(group)


def test_compositions_do_not_cancel_parent(scheduler):
    mech = DummyMechanism("The mechanism", scheduler)

    first = mech.run(park).named("First Child")
    second = mech.run(park).named("Second Child")

    async def group_body():
        fork(first)
        fork(second)
        await park()

    group = mech.run(group_body).named("Group")

    scheduler.schedule(group)
    scheduler.run()

    # The second child interrupts the first.
    assert [c.name for c in scheduler.get_running_commands()] == [
        "Group",
        "Second Child",
    ]


# -- Which hooks run when --------------------------------------------------


def _with_hooks(mechanism, calls, body):
    return (
        mechanism.run(body)
        .when_canceled(lambda: calls.append("on_cancel"))
        .when_exited(lambda: calls.append("on_exit"))
        .named("cmd")
    )


def test_cancel_all_calls_on_cancel_hook_for_running_commands(scheduler):
    calls = []
    command = (
        Command.no_requirements(_park_body)
        .when_canceled(lambda: calls.append("on_cancel"))
        .named("Command")
    )
    scheduler.schedule(command)
    scheduler.run()
    scheduler.cancel_all()
    assert calls == ["on_cancel"]


def test_cancel_all_does_not_call_on_cancel_hook_for_queued_commands(scheduler):
    calls = []
    command = (
        Command.no_requirements(_park_body)
        .when_canceled(lambda: calls.append("on_cancel"))
        .named("Command")
    )
    scheduler.schedule(command)
    # No call to run() before cancel_all().
    scheduler.cancel_all()
    assert calls == []


def test_cancel_all_calls_on_exit_hook_for_running_commands(scheduler):
    calls = []
    command = (
        Command.no_requirements(_park_body)
        .when_exited(lambda: calls.append("on_exit"))
        .named("Command")
    )
    scheduler.schedule(command)
    scheduler.run()
    scheduler.cancel_all()
    assert calls == ["on_exit"]


def test_cancel_all_does_not_call_on_exit_hook_for_queued_commands(scheduler):
    calls = []
    command = (
        Command.no_requirements(_park_body)
        .when_exited(lambda: calls.append("on_exit"))
        .named("Command")
    )
    scheduler.schedule(command)
    scheduler.cancel_all()
    assert calls == []


def test_does_not_run_on_cancel_when_interrupting_on_deck(scheduler):
    mechanism = DummyMechanism("The mechanism", scheduler)
    calls = []
    cmd = _with_hooks(mechanism, calls, _one_tick)
    interrupter = mechanism.run(_one_tick).named("Interrupter")

    scheduler.schedule(cmd)
    scheduler.schedule(interrupter)
    scheduler.run()

    assert "on_cancel" not in calls


def test_does_not_run_on_cancel_when_canceling_on_deck(scheduler):
    mechanism = DummyMechanism("The mechanism", scheduler)
    calls = []
    cmd = _with_hooks(mechanism, calls, _one_tick)

    scheduler.schedule(cmd)
    # Canceling before calling run().
    scheduler.cancel(cmd)
    scheduler.run()

    assert "on_cancel" not in calls


def test_runs_on_cancel_when_interrupting_command(scheduler):
    mechanism = DummyMechanism("The mechanism", scheduler)
    calls = []
    cmd = _with_hooks(mechanism, calls, _park_body)
    interrupter = mechanism.run(_park_body).named("Interrupter")

    scheduler.schedule(cmd)
    scheduler.run()
    scheduler.schedule(interrupter)
    scheduler.run()

    assert "on_cancel" in calls


def test_does_not_run_on_cancel_when_completing(scheduler):
    mechanism = DummyMechanism("The mechanism", scheduler)
    calls = []
    cmd = _with_hooks(mechanism, calls, _one_tick)

    scheduler.schedule(cmd)
    scheduler.run()
    scheduler.run()

    assert not scheduler.is_scheduled_or_running(cmd)
    assert "on_cancel" not in calls


def test_runs_on_cancel_when_canceling(scheduler):
    mechanism = DummyMechanism("The mechanism", scheduler)
    calls = []
    cmd = _with_hooks(mechanism, calls, _one_tick)

    scheduler.schedule(cmd)
    scheduler.run()
    scheduler.cancel(cmd)

    assert "on_cancel" in calls


def test_runs_on_cancel_when_canceling_parent(scheduler):
    mechanism = DummyMechanism("The mechanism", scheduler)
    calls = []
    cmd = _with_hooks(mechanism, calls, _one_tick)
    group = Command.sequence(cmd).named("Seq")

    scheduler.schedule(group)
    scheduler.run()
    scheduler.cancel(group)

    assert "on_cancel" in calls


def test_runs_on_exit_when_canceling_and_when_interrupting(scheduler):
    # on_exit also runs for cancellation, not only for natural completion.
    mechanism = DummyMechanism("The mechanism", scheduler)

    canceled_calls = []
    canceled = _with_hooks(mechanism, canceled_calls, _one_tick)
    scheduler.schedule(canceled)
    scheduler.run()
    scheduler.cancel(canceled)
    assert "on_exit" in canceled_calls

    interrupted_calls = []
    interrupted = _with_hooks(mechanism, interrupted_calls, _park_body)
    interrupter = mechanism.run(_park_body).named("Interrupter")
    scheduler.schedule(interrupted)
    scheduler.run()
    scheduler.schedule(interrupter)
    scheduler.run()
    assert "on_exit" in interrupted_calls


# -- Canceling a command that is executing ---------------------------------
#
# A mounted command has no coroutine to throw into, so cancel() unwinds the
# stack down to it instead and the call doesn't return.


def _hooked(body, calls, name):
    return (
        Command.no_requirements(body)
        .when_exited(lambda: calls.append(f"{name}.on_exit"))
        .when_canceled(lambda: calls.append(f"{name}.on_cancel"))
        .named(name)
    )


def test_a_command_can_cancel_itself(scheduler, watch_events):
    log = watch_events(scheduler)
    ran_after = []

    async def body():
        scheduler.cancel(command)
        ran_after.append(True)

    command = Command.no_requirements(body).named("Self-Canceling Command")
    scheduler.schedule(command)
    scheduler.run()  # must not raise

    assert ran_after == [], "the command should stop at the cancel() call"
    log.assert_canceled(command)
    assert not scheduler.is_scheduled_or_running(command)


def test_canceling_itself_emits_canceled_and_nothing_else(scheduler, watch_events):
    log = watch_events(scheduler)

    async def body():
        scheduler.cancel(command)

    command = Command.no_requirements(body).named("Self-Canceling Command")
    scheduler.schedule(command)
    scheduler.run()

    assert [type(e).__name__ for e in log.events] == [
        "Scheduled",
        "Mounted",
        "Canceled",
    ]


def test_canceling_itself_cancels_its_children(scheduler, watch_events):
    log = watch_events(scheduler)
    child = Command.no_requirements(_park_body).named("Child")

    async def body():
        fork(child)
        scheduler.cancel(command)

    command = Command.no_requirements(body).named("Self-Canceling Command")
    scheduler.schedule(command)
    scheduler.run()

    log.assert_canceled(command)
    log.assert_canceled(child)
    assert not scheduler.is_scheduled_or_running(child)


def test_canceling_itself_does_not_cancel_its_parent(scheduler, watch_events):
    log = watch_events(scheduler)

    async def self_canceler_body():
        scheduler.cancel(self_canceler)

    self_canceler = Command.no_requirements(self_canceler_body).named("Self-Canceler")

    async def parent_body():
        await await_(self_canceler)
        await park()

    parent = Command.no_requirements(parent_body).named("Parent")
    scheduler.schedule(parent)
    scheduler.run()

    log.assert_canceled(self_canceler)
    assert scheduler.get_running_commands() == [parent]


def test_canceling_itself_runs_finally_blocks_then_on_exit_then_on_cancel(scheduler):
    calls = []

    async def body():
        try:
            scheduler.cancel(command)
        finally:
            calls.append("finally")

    command = _hooked(body, calls, "cmd")
    scheduler.schedule(command)
    scheduler.run()

    assert calls == ["finally", "cmd.on_exit", "cmd.on_cancel"]


def test_canceling_itself_is_not_swallowed_by_except_exception(scheduler):
    swallowed = []
    ran_after = []

    async def body():
        try:
            scheduler.cancel(command)
        except Exception as e:  # noqa: BLE001
            swallowed.append(e)
        ran_after.append(True)

    command = Command.no_requirements(body).named("Self-Canceling Command")
    scheduler.schedule(command)
    scheduler.run()

    assert swallowed == []
    assert ran_after == []
    assert not scheduler.is_scheduled_or_running(command)


def test_a_helper_coroutine_can_cancel_the_command_that_awaits_it(scheduler):
    ran_after = []

    async def helper():
        scheduler.cancel(command)
        ran_after.append("helper")

    async def body():
        await helper()
        ran_after.append("body")

    command = Command.no_requirements(body).named("Command")
    scheduler.schedule(command)
    scheduler.run()

    assert ran_after == []
    assert not scheduler.is_scheduled_or_running(command)


def test_a_child_can_cancel_its_parent(scheduler, watch_events):
    log = watch_events(scheduler)
    calls = []

    async def child_body():
        scheduler.cancel(parent)
        calls.append("child ran after cancel")

    child = _hooked(child_body, calls, "child")

    async def parent_body():
        try:
            await await_(child)
            calls.append("parent ran after child")
        finally:
            calls.append("parent finally")

    parent = _hooked(parent_body, calls, "parent")
    scheduler.schedule(parent)
    scheduler.run()  # must not raise

    assert scheduler.get_running_commands() == []
    log.assert_canceled(parent)
    log.assert_canceled(child)
    assert calls == [
        "parent finally",
        "parent.on_exit",
        "parent.on_cancel",
        "child.on_exit",
        "child.on_cancel",
    ]


def test_a_grandchild_can_cancel_its_grandparent(scheduler, watch_events):
    log = watch_events(scheduler)
    calls = []

    async def grandchild_body():
        scheduler.cancel(grandparent)

    grandchild = _hooked(grandchild_body, calls, "grandchild")

    async def child_body():
        try:
            await await_(grandchild)
        finally:
            calls.append("child finally")

    child = _hooked(child_body, calls, "child")

    async def grandparent_body():
        try:
            await await_(child)
        finally:
            calls.append("grandparent finally")

    grandparent = _hooked(grandparent_body, calls, "grandparent")
    scheduler.schedule(grandparent)
    scheduler.run()

    assert scheduler.get_running_commands() == []
    for command in (grandparent, child, grandchild):
        log.assert_canceled(command)
    # Every frame on the way up unwound, innermost first.
    assert calls.index("child finally") < calls.index("grandparent finally")
    for name in ("grandparent", "child", "grandchild"):
        assert calls.count(f"{name}.on_exit") == 1
        assert calls.count(f"{name}.on_cancel") == 1


def test_canceling_an_ancestor_cancels_its_other_children(scheduler):
    sibling = Command.no_requirements(_park_body).named("Sibling")

    async def child_body():
        scheduler.cancel(parent)

    child = Command.no_requirements(child_body).named("Child")

    async def parent_body():
        fork(sibling)
        await await_(child)

    parent = Command.no_requirements(parent_body).named("Parent")
    scheduler.schedule(parent)
    scheduler.run()

    assert scheduler.get_running_commands() == []


def test_canceling_a_command_that_is_not_executing_still_returns(scheduler):
    # Only a command that's on the stack has to be unwound to.
    after = []
    child = Command.no_requirements(_park_body).named("Child")

    async def body():
        fork(child)
        scheduler.cancel(child)
        after.append("ran after cancel")
        await park()

    parent = Command.no_requirements(body).named("Parent")
    scheduler.schedule(parent)
    scheduler.run()

    assert after == ["ran after cancel"]
    assert scheduler.get_running_commands() == [parent]


def test_cancel_all_inside_a_command_cancels_it_and_everything_else(
    scheduler, watch_events
):
    log = watch_events(scheduler)
    calls = []
    other = _hooked(_park_body, calls, "other")
    queued = Command.no_requirements(_park_body).named("Queued")

    async def body():
        fork(other)
        scheduler.schedule(queued)
        try:
            scheduler.cancel_all()
            calls.append("ran after cancel_all")
        finally:
            calls.append("finally")

    stopper = _hooked(body, calls, "stopper")
    scheduler.schedule(stopper)
    scheduler.run()  # must not raise

    assert scheduler.get_running_commands() == []
    assert not scheduler.is_scheduled_or_running(queued)
    for command in (stopper, other, queued):
        log.assert_canceled(command)
    assert "ran after cancel_all" not in calls
    assert calls.count("finally") == 1
    assert calls.count("stopper.on_cancel") == 1
    assert calls.count("other.on_cancel") == 1


def test_cancel_all_from_a_nested_child_cancels_the_whole_composition(
    scheduler, watch_events
):
    log = watch_events(scheduler)
    bystander = Command.no_requirements(_park_body).named("Bystander")

    async def child_body():
        scheduler.cancel_all()

    child = Command.no_requirements(child_body).named("Child")

    async def parent_body():
        await await_(child)
        await park()

    parent = Command.no_requirements(parent_body).named("Parent")
    scheduler.schedule(bystander)
    scheduler.schedule(parent)
    scheduler.run()

    assert scheduler.get_running_commands() == []
    for command in (bystander, parent, child):
        log.assert_canceled(command)


def test_cancel_all_called_from_outside_a_command_is_unchanged(scheduler):
    first = Command.no_requirements(_park_body).named("First")
    second = Command.no_requirements(_park_body).named("Second")
    scheduler.schedule(first)
    scheduler.schedule(second)
    scheduler.run()

    scheduler.cancel_all()

    assert scheduler.get_running_commands() == []


def test_cancel_all_inside_one_scheduler_leaves_another_alone(scheduler):
    other_scheduler = Scheduler.create_independent_scheduler()
    bystander = Command.no_requirements(_park_body).named("Bystander")
    other_scheduler.schedule(bystander)
    other_scheduler.run()

    async def body():
        scheduler.cancel_all()

    scheduler.schedule(Command.no_requirements(body).named("Stopper"))
    scheduler.run()

    assert scheduler.get_running_commands() == []
    assert other_scheduler.get_running_commands() == [bystander]
