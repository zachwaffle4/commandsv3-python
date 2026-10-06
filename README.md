# commandsv3

An **unofficial, community** Python port of [WPILib](https://github.com/wpilibsuite/allwpilib)'s
Commands v3 framework, targeting the new OpMode-based robot structure shared
by FRC (2027) and FTC (2027-2028) on the Systemcore control system. This is
not affiliated with, endorsed by, or produced by FIRST or WPILib.

**This is a proof of concept, not a production-ready library.** APIs may
change without notice, and parts of the Java framework haven't been ported
yet (see [What's missing](#whats-missing)).

## Installation

Not published to PyPI. Install directly from source:

```bash
pip install git+https://github.com/zachwaffle4/commandsv3-python.git
```

Or add it to a `pyproject.toml`:

```toml
dependencies = [
    "commandsv3 @ git+https://github.com/zachwaffle4/commandsv3-python.git",
]
```

Requires Python 3.12+ and `wpilib` 2027.0.0a7 or newer.

## Why

WPILib's command-based framework models robot behavior as **commands**
(units of work) that claim exclusive ownership of **mechanisms** (hardware)
while they run. A **scheduler** ticks every command once per period,
resolves conflicts by priority when two commands need the same mechanism,
and fires **triggers** to start and stop commands based on button presses,
sensor readings, or opmode state.

Commands v3 writes command bodies as plain coroutine-driven functions
instead of split `initialize()`/`execute()`/`end()`/`isFinished()` methods.
WPILib only ships it for Java, because it's built on JDK continuations.
Python has coroutines built in through `async`/`await`, so the same
programming model fits Python naturally. RobotPy doesn't have an equivalent
yet, and this port fills that gap.

## Quick example

```python
import commands3 as cmd3
from commands3 import yield_


class Drivetrain(cmd3.Mechanism):
    def __init__(self):
        super().__init__("Drivetrain")
        # ... motor controllers, etc.

    def arcade_drive(self, forward, rotate):
        async def body():
            while True:
                # apply forward()/rotate() to motors
                await yield_()

        return self.run(body).named("Arcade Drive")


drivetrain = Drivetrain()
drivetrain.set_default_command(drivetrain.arcade_drive(get_forward, get_rotate))

scheduler = cmd3.Scheduler.get_default()
# call scheduler.run() periodically, e.g. from your robot's periodic loop
```

Commands can be composed sequentially or in parallel, cancel each other by
priority, be bound to triggers, and time out:

```python
score = (
    intake.grab()
    .and_then(arm.raise_to_scoring_height())
    .and_then(intake.release())
    .named("Score")
)

auto = drivetrain.drive_to(target).with_timeout(3.0)  # named "Drive To [3.0s timeout]"

cmd3.Trigger(lambda: joystick.get_raw_button(1)).on_true(score)
```

Controller button bindings aren't ported yet, so for now you build triggers
from plain functions that return a bool.

See [`examples/`](examples/) for a complete robot.

## Key pieces

- **`Command`** is a unit of work with a name, required mechanisms, a
  priority, and an `async def` body. Build one with `Command.requiring(...)`,
  `Command.no_requirements(...)`, or a `Mechanism`'s `.run()`.
- **`Mechanism`** is hardware (or any other resource only one command should
  use at a time) that commands claim while running. Subclass it per
  subsystem. By default a mechanism can't be driven while the robot is
  disabled. Commands that need it won't schedule, and running ones are
  canceled when the robot disables. Override `controllable_during_disabled()`
  to return `True` for things that are safe to run while disabled, like LEDs.
- **`Scheduler`** runs commands, resolves conflicts, and drives default
  commands and triggers. `Scheduler.get_default()` is the shared instance
  most code should use.
- **`Trigger`** starts, stops, or toggles commands based on a boolean
  condition (`on_true`, `while_true`, `toggle_on_true`, etc). Combine
  triggers with `.and_()`/`.or_()`/`.negate()` or `&`/`|`/`-`.
- **`commands3.robot_mode_triggers`** has trigger factories for robot state:
  `autonomous()`, `teleop()`, `disabled()`, and `utility()`. There's no
  command-specific robot base class. Extend `wpilib.OpModeRobot` directly
  and call `Scheduler.get_default().run()` from `robot_periodic()`.
  Bindings created while an opmode or robot mode is active are scoped to it
  and torn down when it exits.
- **`yield_()`, `wait()`, `wait_until()`, `fork()`, `await_()`, `all_of()`,
  `any_of()`** are the coroutine helpers you use inside a command body to
  give up control for a tick, pause, and run other commands.

## Differences from the Java version

Names follow Python conventions: `snake_case` methods, and a trailing
underscore where the Java name is a Python keyword (`await_`, `yield_`,
`and_`, `or_`). Beyond naming, a few behaviors differ on purpose:

- **Cancellation runs `finally` blocks.** A command is canceled by raising
  `CommandCancelled` inside its body, so `try`/`finally` cleanup runs.
  Java abandons the body without running it.
- **`except Exception:` won't swallow a cancellation.** `CommandCancelled`
  subclasses `BaseException`, the same way `GeneratorExit` does.
- **A failed fork raises.** If `fork()`, `await_()`, `all_of()`, or
  `any_of()` can't schedule a command, it raises `ForkFailed` and cancels
  the whole composition. Pass `cancel_on_failure=False` to get the result
  back and handle it yourself.
- **Errors say which command failed.** When a command body raises,
  `Scheduler.run()` re-raises the original exception with a note naming
  the command. `failing_command(e)` returns that command.

## What's missing

Not ported yet, listed by their Java names:

- Controller button bindings (`CommandXboxController`, `CommandGamepad`,
  `CommandJoystick`, and the rest of the `button` package)
- `StateMachine`
- `SysIdRoutine`
- Scheduler event listeners (`SchedulerEvent`) and scheduler telemetry
- Sideloaded periodic callbacks (`Scheduler.sideload()`/`addPeriodic()`)
- `Command.onExit()`, `Trigger.ifTrue()`, and the timeout overload of
  `Coroutine.waitUntil()`

## License

BSD-3-Clause, matching WPILib's own license. See [LICENSE.md](LICENSE.md).
