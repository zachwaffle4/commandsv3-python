# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import pytest

from commands3 import (
    DEFAULT_PRIORITY,
    LOWEST_PRIORITY,
    Command,
    Mechanism,
    Scheduler,
    StagedCommandBuilder,
    park,
    yield_,
)


class DummyMechanism(Mechanism):
    pass


def _tick(coro):
    try:
        coro.send(None)
        return False
    except StopIteration:
        return True


async def _noop_body() -> None:
    pass


def test_builder_produces_command_with_expected_fields():
    m1 = DummyMechanism("m1")
    m2 = DummyMechanism("m2")

    command = (
        Command.requiring(m1, m2)
        .executing(_noop_body)
        .with_priority(5)
        .named("Example")
    )

    assert command.name == "Example"
    assert command.requirements == frozenset({m1, m2})
    assert command.priority == 5
    assert command.requires(m1)
    assert not command.requires(DummyMechanism("other"))


def test_no_requirements_defaults_to_empty_set_and_default_priority():
    command = Command.no_requirements(_noop_body).named("Example")

    assert command.requirements == frozenset()
    assert command.priority == DEFAULT_PRIORITY


def test_builder_cannot_be_reused_after_named():
    stage = Command.no_requirements(_noop_body)
    stage.named("First")

    with pytest.raises(RuntimeError):
        stage.named("Second")


def test_conflicts_with_shares_a_requirement():
    m1 = DummyMechanism("m1")
    m2 = DummyMechanism("m2")

    a = Command.requiring(m1).executing(_noop_body).named("A")
    b = Command.requiring(m1, m2).executing(_noop_body).named("B")
    c = Command.no_requirements(_noop_body).named("C")

    assert a.conflicts_with(b)
    assert b.conflicts_with(a)
    assert not a.conflicts_with(c)


def test_priority_comparison():
    m = DummyMechanism()

    low = Command.requiring(m).executing(_noop_body).with_priority(1).named("Low")
    high = Command.requiring(m).executing(_noop_body).with_priority(2).named("High")

    assert low.is_lower_priority_than(high)
    assert not high.is_lower_priority_than(low)


def test_commands_use_identity_equality_not_field_equality():
    m = DummyMechanism()
    a = Command.requiring(m).executing(_noop_body).named("Same Name")
    b = Command.requiring(m).executing(_noop_body).named("Same Name")

    assert a != b
    assert a == a  # noqa: PLR0124 - self-comparison is the point: identity equality


def test_when_canceled_hook_is_stored():
    canceled = []
    command = (
        Command.no_requirements(_noop_body)
        .when_canceled(lambda: canceled.append(True))
        .named("Example")
    )

    command.on_cancel()
    assert canceled == [True]


def test_until_realizes_as_a_race_against_the_end_condition():
    m = DummyMechanism()
    flag = {"done": False}

    async def forever_body():
        while True:
            await yield_()

    command = (
        Command.requiring(m)
        .executing(forever_body)
        .until(lambda: flag["done"])
        .named("Example")
    )

    scheduler = Scheduler.create_independent_scheduler()
    scheduler.schedule(command)
    scheduler.run()
    assert scheduler.is_running(command)

    flag["done"] = True
    scheduler.run()
    assert not scheduler.is_running(command)


def test_mechanism_run_builds_a_command_requiring_it():
    m = DummyMechanism("Arm")
    command = m.run(_noop_body).named("Run Arm")

    assert command.requirements == frozenset({m})


def test_mechanism_run_repeatedly_calls_loop_body_every_tick():
    m = DummyMechanism()
    calls = []

    command = m.run_repeatedly(lambda: calls.append(True)).named("Loop")

    coro = command.body()
    assert _tick(coro) is False
    assert calls == [True]
    assert _tick(coro) is False
    assert calls == [True, True]


def test_mechanism_idle_parks_forever_at_lowest_priority():
    m = DummyMechanism("Arm")
    command = m.idle()

    assert command.name == "Arm[IDLE]"
    assert command.priority == LOWEST_PRIORITY
    assert command.requirements == frozenset({m})

    coro = command.body()
    for _ in range(50):
        assert _tick(coro) is False


def test_builder_with_only_a_body_and_an_end_condition():
    command = (
        StagedCommandBuilder()
        .no_requirements()
        .executing(park)
        .until(lambda: False)
        .named("Name")
    )

    assert command.name == "Name"


def test_builder_accepts_every_option():
    mech = DummyMechanism("Mech")

    command = (
        StagedCommandBuilder()
        .no_requirements()
        .requiring(mech)
        .requiring(mech, mech)
        .executing(park)
        .when_canceled(lambda: None)
        .when_exited(lambda: None)
        .until(lambda: False)
        .with_priority(10)
        .named("Name")
    )

    assert command.name == "Name"


def _built_stages():
    """Builds a command, returning the stages that were used to make it."""
    mech1 = DummyMechanism("Mech 1")
    mech2 = DummyMechanism("Mech 2")
    builder = StagedCommandBuilder()
    requirements_stage = builder.no_requirements()
    name_stage = requirements_stage.executing(_noop_body)
    name_stage.named("cmd")
    return builder, requirements_stage, name_stage, mech1, mech2


@pytest.mark.parametrize(
    "reuse",
    [
        pytest.param(lambda b, r, n, m1, m2: b.no_requirements(), id="starting-none"),
        pytest.param(
            lambda b, r, n, m1, m2: b.requiring(m1, m2), id="starting-requiring"
        ),
        pytest.param(
            lambda b, r, n, m1, m2: b.requiring_all([m1, m2]),
            id="starting-requiring-all",
        ),
        pytest.param(lambda b, r, n, m1, m2: r.requiring(m1), id="requirements-single"),
        pytest.param(
            lambda b, r, n, m1, m2: r.requiring(m1, m2), id="requirements-several"
        ),
        pytest.param(lambda b, r, n, m1, m2: r.executing(_noop_body), id="executing"),
        pytest.param(
            lambda b, r, n, m1, m2: n.when_canceled(lambda: None), id="when-canceled"
        ),
        pytest.param(
            lambda b, r, n, m1, m2: n.when_exited(lambda: None), id="when-exited"
        ),
        pytest.param(lambda b, r, n, m1, m2: n.with_priority(7), id="with-priority"),
        pytest.param(lambda b, r, n, m1, m2: n.until(lambda: True), id="until"),
        pytest.param(lambda b, r, n, m1, m2: n.named("other"), id="named"),
    ],
)
def test_every_builder_stage_throws_after_the_command_is_built(reuse):
    builder, requirements_stage, name_stage, mech1, mech2 = _built_stages()

    with pytest.raises(RuntimeError, match="Command builders cannot be reused"):
        reuse(builder, requirements_stage, name_stage, mech1, mech2)
