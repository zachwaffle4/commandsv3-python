# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""Command and sideload bodies written as async generators, using a bare ``yield``."""

import gc
import warnings

import pytest

from commands3 import (
    Command,
    Mechanism,
    Scheduler,
    failing_command,
    park,
    requires_self,
    wait_until,
)


class DummyMechanism(Mechanism):
    pass


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


def test_bare_yield_suspends_for_one_tick(scheduler):
    ticks = []

    async def body():
        ticks.append(1)
        yield
        ticks.append(2)
        yield
        ticks.append(3)

    command = Command.no_requirements(body).named("Yields")
    scheduler.schedule(command)

    scheduler.run()
    assert ticks == [1]
    scheduler.run()
    assert ticks == [1, 2]
    scheduler.run()
    assert ticks == [1, 2, 3]
    assert not scheduler.is_running(command)


def test_body_can_mix_yield_and_await(scheduler):
    ready = False
    steps = []

    async def body():
        steps.append("start")
        yield
        await wait_until(lambda: ready)
        steps.append("ready")
        yield
        steps.append("end")

    command = Command.no_requirements(body).named("Mixed")
    scheduler.schedule(command)

    scheduler.run()
    scheduler.run()
    scheduler.run()
    assert steps == ["start"]

    ready = True
    scheduler.run()
    assert steps == ["start", "ready"]
    scheduler.run()
    assert steps == ["start", "ready", "end"]
    assert not scheduler.is_running(command)


def test_cancel_at_a_bare_yield_runs_finally_and_on_cancel(scheduler):
    m = DummyMechanism()
    events = []

    async def body():
        try:
            while True:
                yield
        finally:
            events.append("finally")

    command = (
        Command.requiring(m)
        .executing(body)
        .when_canceled(lambda: events.append("on_cancel"))
        .named("Forever")
    )
    scheduler.schedule(command)
    scheduler.run()
    scheduler.run()

    scheduler.cancel(command)

    assert not scheduler.is_running(command)
    assert events == ["finally", "on_cancel"]


def test_cancel_while_awaiting_runs_finally(scheduler):
    cleanup = []

    async def body():
        try:
            yield
            await park()
        finally:
            cleanup.append(True)

    command = Command.no_requirements(body).named("Parks")
    scheduler.schedule(command)
    scheduler.run()
    scheduler.run()

    scheduler.cancel(command)

    assert cleanup == [True]
    assert not scheduler.is_running(command)


def test_cancel_before_starting_does_not_warn(scheduler):
    async def body():
        yield

    command = Command.no_requirements(body).named("NeverStarts")
    scheduler.schedule(command)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        scheduler.cancel(command)
        gc.collect()

    assert not scheduler.is_running(command)


def test_self_cancel_unwinds_out_of_the_body(scheduler):
    events = []
    command = None

    async def body():
        try:
            yield
            scheduler.cancel(command)
            events.append("after cancel")
            yield
        finally:
            events.append("finally")

    command = (
        Command.no_requirements(body)
        .when_canceled(lambda: events.append("on_cancel"))
        .named("CancelsSelf")
    )
    scheduler.schedule(command)
    scheduler.run()
    scheduler.run()

    assert events == ["finally", "on_cancel"]
    assert not scheduler.is_running(command)


def test_error_after_a_yield_is_attributed_to_the_command(scheduler):
    async def body():
        yield
        raise RuntimeError("boom")

    command = Command.no_requirements(body).named("Fails")
    scheduler.schedule(command)
    scheduler.run()

    with pytest.raises(RuntimeError, match="boom") as raised:
        scheduler.run()

    assert failing_command(raised.value) is command
    assert not scheduler.is_running(command)


def test_yielding_a_value_raises_type_error(scheduler):
    cleanup = []

    async def body():
        try:
            yield wait_until(lambda: True)
        finally:
            cleanup.append(True)

    command = Command.no_requirements(body).named("YieldsValue")
    scheduler.schedule(command)

    with pytest.raises(TypeError, match="without a value") as raised:
        scheduler.run()

    assert failing_command(raised.value) is command
    assert cleanup == [True]
    assert not scheduler.is_running(command)


def test_generator_body_can_await_a_child_command(scheduler):
    steps = []

    async def child_body():
        steps.append("child")
        yield
        steps.append("child done")

    child = Command.no_requirements(child_body).named("Child")

    async def parent_body():
        yield
        await child
        steps.append("parent done")

    parent = Command.no_requirements(parent_body).named("Parent")
    scheduler.schedule(parent)

    scheduler.run()
    assert steps == []
    scheduler.run()
    assert steps == ["child"]
    scheduler.run()
    assert steps == ["child", "child done", "parent done"]
    assert not scheduler.is_running(parent)


def test_requires_self_accepts_a_generator_method(scheduler):
    class Counter(Mechanism):
        def __init__(self) -> None:
            super().__init__("Counter")
            self.count = 0

        @requires_self()
        async def count_to(self, n: int):
            while self.count < n:
                self.count += 1
                yield

    counter = Counter()
    command = counter.count_to(3)
    assert command.requires(counter)
    assert command.name == "count_to"

    scheduler.schedule(command)
    for _ in range(4):
        scheduler.run()

    assert counter.count == 3
    assert not scheduler.is_running(command)


def test_sideload_can_be_a_generator(scheduler):
    ticks = []
    cleanup = []

    async def body():
        try:
            for i in range(2):
                ticks.append(i)
                yield
        finally:
            cleanup.append(True)

    scheduler.sideload(body)

    scheduler.run()
    assert ticks == [0]
    scheduler.run()
    assert ticks == [0, 1]
    scheduler.run()
    assert cleanup == [True]
    scheduler.run()
    assert ticks == [0, 1]
