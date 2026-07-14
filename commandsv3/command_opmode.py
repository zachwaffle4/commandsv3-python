# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""The opmode class used to run command-based opmodes registered through ``CommandRobot``/``CommandOpModes``."""

import wpilib

__all__ = ["CommandOpMode"]


class CommandOpMode(wpilib.OpMode):
    """
    Base opmode implementation for command-based opmodes.

    Teams typically don't instantiate this directly; use
    ``CommandRobot``'s or the module-level ``create_*_opmode()`` functions
    in ``command_opmodes.py``, which return an ``OpModeTriggers`` for
    configuring behavior.

    This does not call ``Scheduler.get_default().run()`` itself - call it
    yourself, e.g. from your robot class's ``robot_periodic()``.
    """
