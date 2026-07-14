# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import pytest

from commandsv3 import EventLoop


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


def test_unbinding_while_running_raises():
    loop = EventLoop()

    def naughty_action():
        loop.unbind(naughty_action)

    loop.bind(naughty_action)

    with pytest.raises(RuntimeError):
        loop.poll()
