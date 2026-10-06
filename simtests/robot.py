# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
The robot under test for the simulation suite in `simtests/tests/`.

This is not an example - see `examples/` for that. It exists only to give
`robotpy test` a real robot to start, so the tests in `simtests/tests/` can
exercise commands3 against a real HAL, a real driver station, and a real
periodic loop, rather than against a fake `RobotStateFetcher`.

Run with:

    cd simtests && uv run robotpy test

Run it from this directory with no path arguments. `robotpy test`'s isolated
runner builds its own worker invocations, and passing an explicit test path
makes it re-run the whole file once per worker against a stale opmode
registry.

Everything observable is a plain counter on a mechanism, so tests can assert
on "did this command run during that mode" without any hardware.
"""

import hal
import wpilib
from wpilib.opmodes import OpMode
from wpilib.opmodes import autonomous as autonomous_opmode
from wpilib.opmodes import teleop as teleop_opmode
from wpilib.simulation import DriverStationSim

import commands3 as cmd3
from commands3 import yield_
from commands3.robot_mode_triggers import autonomous, disabled, teleop, utility

#: Names the tests use to select an opmode via `control.step_timing(opmode=)`.
AUTO_OPMODE_NAME = "SimAuto"
TELEOP_OPMODE_NAME = "SimTeleop"


class Counter(cmd3.Mechanism):
    """A mechanism whose only job is to count ticks of the command running on it."""

    def __init__(
        self, name: str, *, controllable_during_disabled: bool = False
    ) -> None:
        super().__init__(name)
        self.ticks = 0
        self._controllable_during_disabled = controllable_during_disabled

    def controllable_during_disabled(self) -> bool:
        return self._controllable_during_disabled

    def counting(self) -> cmd3.Command:
        async def body():
            while True:
                self.ticks += 1
                await yield_()

        return self.run(body).named(f"{self.name} Counting")


class Robot(wpilib.OpModeRobot):
    def __init__(self) -> None:
        super().__init__()

        # The wpilib pytest plugin constructs the robot with the driver
        # station already reporting AUTONOMOUS. A real robot is constructed
        # before the driver station reports any mode at all, and that
        # difference matters: `create_narrowest_scope()` would otherwise
        # scope everything set up below to autonomous, and tear it all down
        # on the first transition out of it. Put the driver station back in
        # the state a real one would be in at startup. `step_timing()` sets
        # the mode explicitly on every step, so this doesn't affect tests.
        DriverStationSim.set_robot_mode(hal.RobotMode.UNKNOWN)
        DriverStationSim.set_opmode(0)
        DriverStationSim.set_enabled(False)
        DriverStationSim.notify_new_data()

        # The default scheduler is a process-wide singleton, so a second
        # robot built in the same process would inherit the first robot's
        # bindings and running commands. `robotpy test` defaults to
        # --isolated (a process per test), but reset anyway so the suite
        # also passes under --no-isolation. The wpilib pytest plugin doesn't
        # know about this scheduler, so it won't reset it for us.
        cmd3.Scheduler._default_scheduler = cmd3.Scheduler()

        # Driven by a default command, so it should run in every enabled
        # mode. It isn't controllable during disabled, so it stops then.
        self.elevator = Counter("Elevator")

        # One per robot mode trigger factory. The disabled marker has to be
        # controllable during disabled, or its command could never run.
        self.auto_marker = Counter("AutoMarker")
        self.teleop_marker = Counter("TeleopMarker")
        self.utility_marker = Counter("UtilityMarker")
        self.disabled_marker = Counter(
            "DisabledMarker", controllable_during_disabled=True
        )

        # Driven by a trigger bound inside an opmode, so its binding should
        # be torn down when that opmode ends.
        self.opmode_marker = Counter("OpModeMarker")
        self.button_pressed = False

        scheduler = cmd3.Scheduler.get_default()
        scheduler.set_default_command(self.elevator, self.elevator.counting())

        # The robot is constructed before the program is marked as started,
        # so the driver station reports no opmode and an unknown robot mode.
        # These bindings therefore land in the global scope and survive
        # every mode change, which is what we want for mode triggers.
        autonomous().while_true(self.auto_marker.counting())
        teleop().while_true(self.teleop_marker.counting())
        utility().while_true(self.utility_marker.counting())
        disabled().while_true(self.disabled_marker.counting())

    def robot_periodic(self) -> None:
        cmd3.Scheduler.get_default().run()


@autonomous_opmode(name=AUTO_OPMODE_NAME)
class SimAuto(OpMode):
    def __init__(self, robot: Robot) -> None:
        super().__init__()
        self.robot = robot


@teleop_opmode(name=TELEOP_OPMODE_NAME)
class SimTeleop(OpMode):
    def __init__(self, robot: Robot) -> None:
        super().__init__()
        self.robot = robot

    def start(self) -> None:
        # Created while this opmode is active, so the binding is scoped to
        # it and should be cleaned up when the opmode ends.
        trigger = cmd3.Trigger(lambda: self.robot.button_pressed)
        trigger.while_true(self.robot.opmode_marker.counting())
