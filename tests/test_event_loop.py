# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import gc
import weakref

import pytest

from commands3 import EventLoop


def test_bound_actions_run_on_poll():
    loop = EventLoop()
    calls = []
    loop.bind(lambda: calls.append("a"))
    loop.bind(lambda: calls.append("b"))

    loop.poll()

    assert calls == ["a", "b"]


def test_unbind_stops_an_action_from_running():
    loop = EventLoop()
    calls = []

    def action():
        calls.append(True)

    loop.bind(action)
    loop.poll()
    assert calls == [True]

    loop.unbind(action)
    loop.poll()
    assert calls == [True]


def test_unbind_is_a_no_op_if_not_bound():
    loop = EventLoop()
    loop.unbind(lambda: None)  # should not raise


def test_clear_removes_all_bindings():
    loop = EventLoop()
    calls = []
    loop.bind(lambda: calls.append(True))
    loop.clear()

    loop.poll()

    assert calls == []


def test_binding_while_running_raises():
    loop = EventLoop()

    def naughty_action():
        loop.bind(lambda: None)

    loop.bind(naughty_action)

    with pytest.raises(RuntimeError):
        loop.poll()


class _Counter:
    def __init__(self):
        self.count = 0

    def tick(self):
        self.count += 1


def test_bind_weak_runs_while_the_action_is_alive():
    loop = EventLoop()
    counter = _Counter()
    loop.bind_weak(counter.tick)

    loop.poll()
    loop.poll()

    assert counter.count == 2
    assert loop.is_bound(counter.tick)


def test_bind_weak_does_not_keep_the_owner_alive():
    loop = EventLoop()
    counter = _Counter()
    ref = weakref.ref(counter)
    calls = []
    loop.bind_weak(counter.tick)
    loop.bind(lambda: calls.append(True))

    del counter
    gc.collect()
    loop.poll()

    assert ref() is None
    assert calls == [True]


def test_bind_weak_of_a_plain_function_does_not_keep_it_alive():
    loop = EventLoop()

    def action():
        pass

    ref = weakref.ref(action)
    loop.bind_weak(action)

    del action
    gc.collect()
    loop.poll()

    assert ref() is None


def test_strong_bind_keeps_the_owner_alive():
    loop = EventLoop()
    counter = _Counter()
    ref = weakref.ref(counter)
    loop.bind(counter.tick)

    del counter
    gc.collect()
    loop.poll()

    owner = ref()
    assert owner is not None
    assert owner.count == 1


def test_unbind_removes_a_weakly_bound_bound_method():
    loop = EventLoop()
    counter = _Counter()
    loop.bind_weak(counter.tick)

    loop.unbind(counter.tick)
    loop.poll()

    assert counter.count == 0
    assert not loop.is_bound(counter.tick)


def test_weak_bindings_run_in_bind_order_with_strong_ones():
    loop = EventLoop()
    calls = []

    def weak_action():
        calls.append("weak")

    loop.bind(lambda: calls.append("strong 1"))
    loop.bind_weak(weak_action)
    loop.bind(lambda: calls.append("strong 2"))

    loop.poll()

    assert calls == ["strong 1", "weak", "strong 2"]


def test_bind_weak_while_running_raises():
    loop = EventLoop()

    def naughty_action():
        loop.bind_weak(lambda: None)

    loop.bind(naughty_action)

    with pytest.raises(RuntimeError):
        loop.poll()


def test_unbinding_while_running_raises():
    loop = EventLoop()

    def naughty_action():
        loop.unbind(naughty_action)

    loop.bind(naughty_action)

    with pytest.raises(RuntimeError):
        loop.poll()
