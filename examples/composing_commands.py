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

The compositions are methods of `Routines`, which owns the mechanisms the
way a robot class does. On a real robot they'd be methods of `Robot`. The
coroutine versions decorate a nested `body` function, so `requires=` can name
`self.intake` and `self.arm`: they exist by the time the method runs.
"""

from wpilib import simulation

import commands3 as cmd3
from commands3 import all_of, any_of, command, fork

from .arm import Arm
from .intake import Intake
from .light import Light

_TICK_SECONDS = 0.02


class Routines:
    def __init__(self) -> None:
        self.intake = Intake()
        self.arm = Arm()
        self.light = Light()

    def score_by_composition(self) -> cmd3.Command:
        """Grab, then lower the arm, then release - built by chaining commands."""
        return (
            self.intake.grab()
            .and_then(self.arm.lower_arm())
            .and_then(self.intake.release())
            .named("Score (composed)")
        )

    def score_by_coroutine(self) -> cmd3.Command:
        """The same sequence, written as a single coroutine body."""

        @command(name="Score (coroutine)", requires=(self.intake, self.arm))
        async def body() -> None:
            await self.intake.grab()
            await self.arm.lower_arm()
            await self.intake.release()

        return body()

    def prep_by_composition(self) -> cmd3.Command:
        """Grab and lower the arm at the same time - built with `.along_with()`."""
        return (
            self.arm.lower_arm().along_with(self.intake.grab()).named("Prep (composed)")
        )

    def prep_by_coroutine(self) -> cmd3.Command:
        """The same parallel behavior, written as a single coroutine body."""

        @command(name="Prep (coroutine)", requires=(self.intake, self.arm))
        async def body() -> None:
            await all_of([self.arm.lower_arm(), self.intake.grab()])

        return body()

    def score_with_status_light(self) -> cmd3.Command:
        """
        Scores as above, but also blinks a status light for as long as
        scoring takes. `fork()` starts the light without waiting on it; it's
        tied to this command's lifetime, so it's canceled automatically once
        scoring finishes (or is itself interrupted). Named
        "Routines.score_with_status_light", after the method `body` is in.
        """

        @command(requires=(self.intake, self.arm))
        async def body() -> None:
            fork(self.light.blink())
            await self.intake.grab()
            await self.arm.lower_arm()
            await self.intake.release()

        return body()

    def first_driver_input(self) -> cmd3.Command:
        """Whichever finishes first, cancel the other - built with `Command.race()`."""
        return cmd3.Command.race(self.intake.grab(), self.arm.lower_arm()).named(
            "First Driver Input"
        )

    def first_driver_input_coroutine(self) -> cmd3.Command:
        """The same race, written as a single coroutine body."""

        @command(
            name="First Driver Input (coroutine)", requires=(self.intake, self.arm)
        )
        async def body() -> None:
            await any_of([self.intake.grab(), self.arm.lower_arm()])

        return body()


def main() -> None:
    routines = Routines()
    scheduler = cmd3.Scheduler.get_default()

    # Controls simulated time directly instead of relying on real wall-clock
    # delays, so `wait()`/`Timer`-based commands complete deterministically.
    simulation.pause_timing()

    for build in (
        routines.score_by_composition,
        routines.score_by_coroutine,
        routines.prep_by_composition,
        routines.prep_by_coroutine,
        routines.score_with_status_light,
        routines.first_driver_input,
        routines.first_driver_input_coroutine,
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
