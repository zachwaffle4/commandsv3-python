# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import dataclasses
import time

import pytest
import wpilib
from wpilib import simulation
from wpilib.sysid import State

from commands3 import Mechanism, Scheduler, SysIdRoutine

FORWARD = SysIdRoutine.Direction.FORWARD
REVERSE = SysIdRoutine.Direction.REVERSE


class DummyMechanism(Mechanism):
    pass


class Recorder:
    """Stands in for the hardware: records every callback in call order."""

    def __init__(self):
        self.calls = []

    def drive(self, volts):
        self.calls.append(("drive", volts))

    def log(self, log):
        self.calls.append(("log", log))

    def record_state(self, state):
        self.calls.append(("state", state))

    def drives(self):
        return [value for kind, value in self.calls if kind == "drive"]

    def states(self):
        return [value for kind, value in self.calls if kind == "state"]


@pytest.fixture(autouse=True)
def paused_time():
    """Pauses simulated time so a test decides exactly how much passes."""
    simulation.pause_timing()
    yield
    simulation.resume_timing()


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


@pytest.fixture
def recorder():
    return Recorder()


@pytest.fixture
def routine(recorder):
    return SysIdRoutine(
        SysIdRoutine.Config(record_state=recorder.record_state),
        SysIdRoutine.SysIdMechanism(recorder.drive, recorder.log, DummyMechanism()),
    )


def run_for_one_second(scheduler, command):
    """Runs a command for two ticks, then one more a simulated second later, then cancels."""
    scheduler.schedule(command)
    scheduler.run()
    scheduler.run()
    simulation.step_timing(1.0)
    scheduler.run()
    scheduler.cancel(command)


def test_each_tick_drives_then_logs_then_records_state(scheduler, recorder, routine):
    command = routine.quasistatic(FORWARD)
    scheduler.schedule(command)
    scheduler.run()

    assert recorder.calls == [
        ("drive", 0.0),
        ("log", routine),
        ("state", State.QUASISTATIC_FORWARD),
    ]


def test_ending_zeroes_the_drive_and_records_state_none(scheduler, recorder, routine):
    command = routine.quasistatic(FORWARD)
    scheduler.schedule(command)
    scheduler.run()
    recorder.calls.clear()

    scheduler.cancel(command)

    assert recorder.calls == [("drive", 0.0), ("state", State.NONE)]


@pytest.mark.parametrize(
    "factory, direction, expected",
    [
        ("quasistatic", FORWARD, State.QUASISTATIC_FORWARD),
        ("quasistatic", REVERSE, State.QUASISTATIC_REVERSE),
        ("dynamic", FORWARD, State.DYNAMIC_FORWARD),
        ("dynamic", REVERSE, State.DYNAMIC_REVERSE),
    ],
)
def test_tests_declare_the_correct_state(
    scheduler, recorder, routine, factory, direction, expected
):
    run_for_one_second(scheduler, getattr(routine, factory)(direction))

    assert set(recorder.states()) == {expected, State.NONE}
    assert recorder.states()[-1] is State.NONE
    assert recorder.states().count(State.NONE) == 1


@pytest.mark.parametrize(
    "factory, direction, expected",
    [
        # Time is paused for the first two ticks, then a simulated second
        # passes; the quasistatic ramp (1 V/s) is at 1 V by the third tick
        # and the dynamic step is at 7 V throughout. The last drive is the
        # stop.
        ("quasistatic", FORWARD, [0.0, 0.0, 1.0, 0.0]),
        ("quasistatic", REVERSE, [0.0, 0.0, -1.0, 0.0]),
        ("dynamic", FORWARD, [7.0, 7.0, 7.0, 0.0]),
        ("dynamic", REVERSE, [-7.0, -7.0, -7.0, 0.0]),
    ],
)
def test_tests_output_the_correct_voltage(
    scheduler, recorder, routine, factory, direction, expected
):
    run_for_one_second(scheduler, getattr(routine, factory)(direction))

    assert recorder.drives() == pytest.approx(expected)


def test_quasistatic_voltage_ramps_linearly(scheduler, recorder, routine):
    scheduler.schedule(routine.quasistatic(FORWARD))
    scheduler.run()
    for _ in range(4):
        simulation.step_timing(0.25)
        scheduler.run()

    assert recorder.drives() == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0])


def test_dynamic_voltage_is_constant(scheduler, recorder, routine):
    scheduler.schedule(routine.dynamic(FORWARD))
    scheduler.run()
    for _ in range(3):
        simulation.step_timing(0.25)
        scheduler.run()

    assert recorder.drives() == [7.0, 7.0, 7.0, 7.0]


def test_config_values_are_used(scheduler, recorder):
    routine = SysIdRoutine(
        SysIdRoutine.Config(
            ramp_rate=2.0, step_voltage=3.0, record_state=recorder.record_state
        ),
        SysIdRoutine.SysIdMechanism(recorder.drive, recorder.log, DummyMechanism()),
    )

    run_for_one_second(scheduler, routine.quasistatic(FORWARD))
    assert recorder.drives()[-2] == pytest.approx(2.0)

    recorder.calls.clear()
    run_for_one_second(scheduler, routine.dynamic(REVERSE))
    assert recorder.drives()[-2] == pytest.approx(-3.0)


def test_test_ends_by_itself_after_the_timeout(scheduler, recorder):
    routine = SysIdRoutine(
        SysIdRoutine.Config(timeout=2.0, record_state=recorder.record_state),
        SysIdRoutine.SysIdMechanism(recorder.drive, recorder.log, DummyMechanism()),
    )
    command = routine.dynamic(FORWARD)

    scheduler.schedule(command)
    scheduler.run()
    simulation.step_timing(1.0)
    scheduler.run()
    assert scheduler.is_running(command)

    simulation.step_timing(1.5)
    scheduler.run()

    assert not scheduler.is_running(command)
    assert recorder.calls[-2:] == [("drive", 0.0), ("state", State.NONE)]
    assert recorder.drives().count(0.0) == 1


def test_commands_require_the_mechanism(recorder):
    mechanism = DummyMechanism()
    routine = SysIdRoutine(
        SysIdRoutine.Config(),
        SysIdRoutine.SysIdMechanism(recorder.drive, recorder.log, mechanism),
    )

    for command in (
        routine.quasistatic(FORWARD),
        routine.quasistatic(REVERSE),
        routine.dynamic(FORWARD),
        routine.dynamic(REVERSE),
    ):
        assert command.requirements == frozenset({mechanism})


def test_command_names_include_the_state_and_mechanism_name(recorder):
    routine = SysIdRoutine(
        SysIdRoutine.Config(),
        SysIdRoutine.SysIdMechanism(recorder.drive, recorder.log, DummyMechanism()),
    )

    assert (
        routine.quasistatic(FORWARD).name == "sysid-quasistatic-forward-DummyMechanism"
    )
    assert (
        routine.quasistatic(REVERSE).name == "sysid-quasistatic-reverse-DummyMechanism"
    )
    assert routine.dynamic(FORWARD).name == "sysid-dynamic-forward-DummyMechanism"
    assert routine.dynamic(REVERSE).name == "sysid-dynamic-reverse-DummyMechanism"


def test_an_explicit_name_overrides_the_mechanism_name(recorder):
    routine = SysIdRoutine(
        SysIdRoutine.Config(),
        SysIdRoutine.SysIdMechanism(
            recorder.drive, recorder.log, DummyMechanism(), name="elevator"
        ),
    )

    assert routine.dynamic(FORWARD).name == "sysid-dynamic-forward-elevator"


def test_a_missing_log_callback_records_nothing_and_does_not_fail(scheduler, recorder):
    routine = SysIdRoutine(
        SysIdRoutine.Config(record_state=recorder.record_state),
        SysIdRoutine.SysIdMechanism(recorder.drive, None, DummyMechanism()),
    )

    run_for_one_second(scheduler, routine.dynamic(FORWARD))

    assert "log" not in {kind for kind, _ in recorder.calls}
    assert recorder.drives()[-1] == 0.0


def test_config_defaults():
    config = SysIdRoutine.Config()

    assert config.ramp_rate == SysIdRoutine.Config.DEFAULT_RAMP_RATE == 1.0
    assert config.step_voltage == SysIdRoutine.Config.DEFAULT_STEP_VOLTAGE == 7.0
    assert config.timeout == SysIdRoutine.Config.DEFAULT_TIMEOUT == 10.0
    assert config.record_state is None


def test_config_is_immutable():
    config = SysIdRoutine.Config()

    with pytest.raises(dataclasses.FrozenInstanceError):
        config.timeout = 1.0  # ty: ignore[invalid-assignment]


@pytest.fixture
def data_log(tmp_path):
    """Points the WPILog data log at a temp directory, and stops it afterwards.

    Leaving the log running makes robotpy abort the interpreter at exit, and
    stopping it twice starts a fresh log in the working directory, so the
    stop happens exactly once, here.
    """
    wpilib.DataLogManager.start(str(tmp_path))
    yield tmp_path
    wpilib.DataLogManager.stop()


def _wait_for_log_to_contain(directory, expected: list[bytes], timeout=5.0):
    """The log is written by a background thread, so poll rather than assume."""
    deadline = time.monotonic() + timeout
    contents = b""
    while time.monotonic() < deadline:
        logs = list(directory.glob("*.wpilog"))
        contents = logs[0].read_bytes() if logs else b""
        if all(fragment in contents for fragment in expected):
            return contents
        time.sleep(0.05)
    return contents


def test_without_a_record_state_callback_the_state_goes_to_the_wpilog(
    scheduler, data_log
):
    routine = SysIdRoutine(
        SysIdRoutine.Config(),
        SysIdRoutine.SysIdMechanism(
            lambda volts: None, None, DummyMechanism(), name="wpilog-test"
        ),
    )

    run_for_one_second(scheduler, routine.quasistatic(FORWARD))

    expected = [b"sysid-test-state-wpilog-test", b"quasistatic-forward", b"none"]
    contents = _wait_for_log_to_contain(data_log, expected)
    for fragment in expected:
        assert fragment in contents
