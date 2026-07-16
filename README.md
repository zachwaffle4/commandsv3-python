# commandsv3

An **unofficial, community** Python port of [WPILib](https://github.com/wpilibsuite/allwpilib)'s
Commands v3 framework, targeting the new OpMode-based robot structure shared
by FRC (2027) and FTC (2027-2028) on the Systemcore control system. This is
not affiliated with, endorsed by, or produced by FIRST or WPILib.

**This is a proof of concept, not a production-ready library.** APIs may
change without notice, and several pieces of the original Java framework
haven't been ported.

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

Requires Python 3.12+ and `wpilib` 2027.0.0a6.post4 or newer.

## Why

WPILib's command-based framework models robot behavior as **commands**
(units of work) that claim exclusive ownership of **mechanisms** (hardware)
while they run. A **scheduler** ticks every command once per period,
resolves conflicts by priority when two commands need the same mechanism,
and fires **triggers** to start and stop commands based on button presses,
sensor readings, or opmode state.

Commands v3 (Java-only in upstream WPILib, since it depends on JDK
continuations) writes command bodies as plain coroutine-driven functions
instead of split `initialize()`/`execute()`/`end()`/`isFinished()` methods.
Python has native coroutine support via `async`/`await`, so this port aims
to bring that same programming model to Python - RobotPy doesn't have an
equivalent yet.

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
score = intake.grab().and_then(arm.raise_to_scoring_height()).and_then(intake.release()).named("Score")

auto = drivetrain.drive_to(target).with_timeout(3.0).named("Auto")

cv3.Trigger(lambda: joystick.getRawButton(1)).on_true(score)
```

(HID button bindings like `CommandXboxController` haven't been ported yet -
see [PORTING_STATUS.md](PORTING_STATUS.md) - so triggers are built from
plain boolean-returning callables for now.)

## Key pieces

- **`Command`** - a unit of work with a name, required mechanisms, priority,
  and an `async def` body. Built via `Command.requiring(...)`/
  `Command.no_requirements(...)` or a `Mechanism`'s `.run()`.
- **`Mechanism`** - hardware (or any other exclusively-ownable resource) that
  commands claim while running. Subclass this per subsystem.
- **`Scheduler`** - runs commands, resolves conflicts, and drives default
  commands and triggers. `Scheduler.get_default()` is the shared instance
  most code should use.
- **`Trigger`** - starts, stops, or toggles commands based on a boolean
  condition (`on_true`, `while_true`, `toggle_on_true`, etc), composable
  with `.and_()`/`.or_()`/`.negate()`.
- **`CommandRobot`/`CommandOpModes`/`OpModeTriggers`** - integration with
  WPILib's OpMode model: register command-based opmodes and get triggers
  for when they're selected, enabled, or disabled.
- **`yield_()`/`wait()`/`wait_until()`/`fork()`/`await_()`** - the
  coroutine primitives used inside a command's body to yield control, pause,
  and compose with other commands.

## Divergences from the Java implementation

Python's coroutine model, garbage collection, and available WPILib bindings
differ from Java's in a few places that require deliberate design choices
rather than a line-for-line port - notably how command cancellation
interacts with `try`/`finally`, and how `EventLoop` unbinding is
implemented. 

## License

BSD-3-Clause, matching WPILib's own license - see [LICENSE.md](LICENSE.md).
