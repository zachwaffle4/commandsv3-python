# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A SysId characterization routine built from commands."""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Callable
from typing import ClassVar

import wpilib
from wpilib.sysid import State, SysIdRoutineLog

from ..command import Command
from ..coroutine import yield_
from ..mechanism import Mechanism

__all__ = ["SysIdRoutine"]


class SysIdRoutine(SysIdRoutineLog):
    """
    A SysId characterization routine for a single mechanism. Mechanisms may
    have multiple motors.

    A single subsystem may have multiple mechanisms, but mechanisms should not
    share test routines. Each complete test of a mechanism should have its own
    ``SysIdRoutine`` instance, since the log name of the recorded data is
    determined by the mechanism name.

    The test state (e.g. ``"quasistatic-forward"``) is logged once per
    iteration during test execution, and once with state ``"none"`` when a
    test ends. Motor frames are logged every iteration during test execution.

    Timestamps are not coordinated across data, so motor frames and test
    state tags may be recorded on different log frames. Because frame
    alignment is not guaranteed, SysId parses the log by using the test state
    flag to determine the timestamp range for each section of the test, and
    then extracts the motor frames within the valid timestamp ranges. If a
    given test was run multiple times in a single logfile, the user will need
    to select which of the tests to use for the fit in the analysis tool.

    Voltages are in volts, ramp rates in volts per second, and durations in
    seconds.
    """

    @dataclasses.dataclass(frozen=True)
    class Config:
        """
        Hardware-independent configuration for a SysId test routine. The
        default instance, ``SysIdRoutine.Config()``, uses the default values
        and records to the WPILog data log.
        """

        DEFAULT_RAMP_RATE: ClassVar[float] = 1.0
        """Default voltage ramp rate used in quasistatic test routines: 1 volt per second."""

        DEFAULT_STEP_VOLTAGE: ClassVar[float] = 7.0
        """Default step voltage used in dynamic test routines: 7 volts."""

        DEFAULT_TIMEOUT: ClassVar[float] = 10.0
        """Default timeout used to automatically end test routine commands: 10 seconds."""

        ramp_rate: float = DEFAULT_RAMP_RATE
        """The voltage ramp rate used for quasistatic test routines, in volts per second."""

        step_voltage: float = DEFAULT_STEP_VOLTAGE
        """The step voltage output used for dynamic test routines, in volts."""

        timeout: float = DEFAULT_TIMEOUT
        """Safety timeout for the test routine commands, in seconds."""

        record_state: Callable[[State], None] | None = None
        """
        Optional handle for recording test state in a third-party logging
        solution. If provided, the test routine state is passed to this
        callback instead of being logged in the WPILog.
        """

    class SysIdMechanism:
        """
        A mechanism to be characterized by a SysId routine. Defines the
        callbacks the routine needs to control and record data from the
        mechanism.
        """

        def __init__(
            self,
            drive: Callable[[float], None],
            log: Callable[[SysIdRoutineLog], None] | None,
            mechanism: Mechanism,
            name: str | None = None,
        ) -> None:
            """
            :param drive: Sends the SysId-specified drive signal, in volts, to
                the mechanism's motors during test routines.
            :param log: Records measured data of the mechanism's motors during
                test routines. To record data, call ``motor(motor_name)`` on
                the supplied ``SysIdRoutineLog``, then call one or more of the
                chainable logging methods (e.g. ``voltage``) on the returned
                ``MotorLog``. Multiple motors can be logged in a single
                callback by calling ``motor`` multiple times. ``None`` records
                nothing.
            :param mechanism: The mechanism containing the motor(s) being
                characterized. It is declared as a requirement of the returned
                test commands.
            :param name: The name of the mechanism being tested. It is
                appended to the log entry title for the routine's test state,
                e.g. ``"sysid-test-state-mechanism"``. Defaults to the name of
                ``mechanism``.
            """
            self.drive = drive
            self.log: Callable[[SysIdRoutineLog], None] = (
                log if log is not None else _ignore_log
            )
            self.mechanism = mechanism
            self.name = name if name is not None else mechanism.name

    class Direction(enum.Enum):
        """Motor direction for a SysId test."""

        FORWARD = enum.auto()
        REVERSE = enum.auto()

    def __init__(
        self, config: SysIdRoutine.Config, mechanism: SysIdRoutine.SysIdMechanism
    ) -> None:
        """
        :param config: Hardware-independent parameters for the SysId routine.
        :param mechanism: Hardware interface for the SysId routine.
        """
        super().__init__(mechanism.name)
        self._config = config
        self._mechanism = mechanism
        self._record_state: Callable[[State], None] = (
            config.record_state
            if config.record_state is not None
            else self.record_state
        )

    def quasistatic(self, direction: SysIdRoutine.Direction) -> Command:
        """
        A command that runs a quasistatic test in the given direction: the
        drive voltage ramps up from zero at the configured ramp rate.

        The command calls the ``drive`` and ``log`` callbacks supplied at
        routine construction once per tick. When it ends for any reason, the
        ``drive`` callback is called with 0 volts.

        :param direction: The direction in which to run the test.
        """
        sign = _output_sign(direction)
        state = (
            State.QUASISTATIC_FORWARD
            if direction is SysIdRoutine.Direction.FORWARD
            else State.QUASISTATIC_REVERSE
        )
        ramp_rate = self._config.ramp_rate
        return self._test_command(state, lambda elapsed: ramp_rate * elapsed * sign)

    def dynamic(self, direction: SysIdRoutine.Direction) -> Command:
        """
        A command that runs a dynamic test in the given direction: the drive
        voltage steps straight to the configured step voltage.

        The command calls the ``drive`` and ``log`` callbacks supplied at
        routine construction once per tick. When it ends for any reason, the
        ``drive`` callback is called with 0 volts.

        :param direction: The direction in which to run the test.
        """
        output = self._config.step_voltage * _output_sign(direction)
        state = (
            State.DYNAMIC_FORWARD
            if direction is SysIdRoutine.Direction.FORWARD
            else State.DYNAMIC_REVERSE
        )
        return self._test_command(state, lambda _elapsed: output)

    def _test_command(
        self, state: State, output_at: Callable[[float], float]
    ) -> Command:
        mechanism = self._mechanism
        timeout = self._config.timeout

        async def body() -> None:
            timer = wpilib.Timer()
            timer.start()
            while not timer.has_elapsed(timeout):
                mechanism.drive(output_at(timer.get()))
                mechanism.log(self)
                self._record_state(state)
                await yield_()

        state_name = SysIdRoutineLog.state_enum_to_string(state)
        return (
            mechanism.mechanism.run(body)
            .when_exited(self._stop_routine)
            .named(f"sysid-{state_name}-{mechanism.name}")
        )

    def _stop_routine(self) -> None:
        self._mechanism.drive(0.0)
        self._record_state(State.NONE)


def _output_sign(direction: SysIdRoutine.Direction) -> float:
    return 1.0 if direction is SysIdRoutine.Direction.FORWARD else -1.0


def _ignore_log(_log: SysIdRoutineLog) -> None:
    pass
