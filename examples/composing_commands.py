# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Two ways to compose the same behavior out of an intake and an arm: the
builder methods (`.and_then()`/`.along_with()`/`Command.race()`), and a
single coroutine body using `fork`/`await`/`all_of`/`any_of`. Both produce
an equivalent `Command` - pick whichever reads more clearly for the
situation; the coroutine form is handy when steps need to share local state
or branch on intermediate results. `Command.__await__` means `await
some_command` schedules it and waits for completion directly, no separate
`await_()` call needed.
"""

import wpilib.simulation as simulation

import commands3 as cmd3
from commands3 import all_of, any_of, fork

from .arm import Arm
from .intake import Intake
from .light import Light

_TICK_SECONDS = 0.02


def score_by_composition(intake: Intake, arm: Arm) -> cmd3.Command:
    """Grab, then lower the arm, then release - built by chaining commands."""
    return (
        intake.grab()
        .and_then(arm.lower_arm())
        .and_then(intake.release())
        .named("Score (composed)")
    )


def score_by_coroutine(intake: Intake, arm: Arm) -> cmd3.Command:
    """The same sequence, written as a single coroutine body."""

    @cmd3.requiring("Score (coroutine)", intake, arm)
    async def body() -> None:
        await intake.grab()
        await arm.lower_arm()
        await intake.release()

    return body()


def prep_by_composition(intake: Intake, arm: Arm) -> cmd3.Command:
    """Grab and lower the arm at the same time - built with `.along_with()`."""
    return arm.lower_arm().along_with(intake.grab()).named("Prep (composed)")


def prep_by_coroutine(intake: Intake, arm: Arm) -> cmd3.Command:
    """The same parallel behavior, written as a single coroutine body."""

    @cmd3.requiring("Prep (coroutine)", intake, arm)
    async def body() -> None:
        await all_of([arm.lower_arm(), intake.grab()])

    return body()


def score_with_status_light(intake: Intake, arm: Arm, light: Light) -> cmd3.Command:
    """
    Scores as above, but also blinks a status light for as long as scoring
    takes. `fork()` starts the light without waiting on it; it's tied to
    this command's lifetime, so it's canceled automatically once scoring
    finishes (or is itself interrupted).
    """

    @cmd3.requiring("Score With Light", intake, arm)
    async def body() -> None:
        fork(light.blink())
        await intake.grab()
        await arm.lower_arm()
        await intake.release()

    return body()


def first_driver_input(intake: Intake, arm: Arm) -> cmd3.Command:
    """Whichever finishes first, cancel the other - built with `Command.race()`."""
    return cmd3.Command.race(intake.grab(), arm.lower_arm()).named("First Driver Input")


def first_driver_input_coroutine(intake: Intake, arm: Arm) -> cmd3.Command:
    """The same race, written as a single coroutine body."""

    @cmd3.requiring("First Driver Input (coroutine)", intake, arm)
    async def body() -> None:
        await any_of([intake.grab(), arm.lower_arm()])

    return body()


def main() -> None:
    intake = Intake()
    arm = Arm()
    light = Light()
    scheduler = cmd3.Scheduler.get_default()

    # Controls simulated time directly instead of relying on real wall-clock
    # delays, so `wait()`/`Timer`-based commands complete deterministically.
    simulation.pause_timing()

    for build in (
        lambda: score_by_composition(intake, arm),
        lambda: score_by_coroutine(intake, arm),
        lambda: prep_by_composition(intake, arm),
        lambda: prep_by_coroutine(intake, arm),
        lambda: score_with_status_light(intake, arm, light),
        lambda: first_driver_input(intake, arm),
        lambda: first_driver_input_coroutine(intake, arm),
    ):
        command = build()
        scheduler.schedule(command)
        for _ in range(150):
            simulation.step_timing(_TICK_SECONDS)
            scheduler.run()
        print(
            f"{command.name}: finished={not scheduler.is_scheduled_or_running(command)}"
        )


if __name__ == "__main__":
    main()
