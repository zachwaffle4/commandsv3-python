# Stage 1B: REV solution

A Python port of the frcsoftware.org Stage 1B REV solution: a differential
drivetrain, an intake/launcher, and a feeder on SPARK MAXes, with a fuel
visualization for AdvantageScope.

This is a standalone RobotPy project. Run everything from this directory:

```bash
python -m robotpy sim    # simulate (simgui-ds.json maps the keyboard to the Xbox controller)
python -m robotpy test   # behavior tests in tests/
```

Inside this repo you can use the root environment instead:
`uv run --project ../.. python -m robotpy sim`.

Load `AdvantageScopeLayout.json` in AdvantageScope to see the robot and fuel.

As with the original, this code has only been tested in simulation. Don't run
it on a real robot.

## Layout

| Java                                  | Python                                 |
| ------------------------------------- | -------------------------------------- |
| `Robot.java`                          | `robot.py`                             |
| `mechanisms/*.java`                   | `mechanisms/*.py`                      |
| `opmode/*.java`                       | `opmodes/*.py` (auto-discovered)       |
| `simulation/*.java`                   | `simulation/*.py`                      |
| `Main.java`                           | not needed                             |
