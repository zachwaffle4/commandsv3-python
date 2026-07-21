# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A robot base class for registering command-based opmodes directly from a robot's constructor."""

from __future__ import annotations

import hal
import wpilib
import wpiutil

from .command_opmode import CommandOpMode
from .opmode_triggers import OpModeTriggers

__all__ = ["CommandRobot"]


class CommandRobot(wpilib.OpModeRobotBase):
    """
    Base robot class for command-based opmode registration. Use the
    ``create_*_opmode()`` methods to create command-aware opmode descriptors
    and register them in autonomous, teleoperated, or utility mode groups.

    After adding opmodes, call ``wpilib.RobotState.publish_opmodes()`` to
    publish the updated opmode list.

    Extends ``wpilib.OpModeRobotBase`` rather than the ``wpilib.OpModeRobot``
    convenience wrapper, since that wrapper's ``__init__`` doesn't accept a
    custom period at all.
    """

    def __init__(self, period: float | None = None) -> None:
        """Creates a command robot, optionally with a custom periodic loop period in seconds."""
        # Not defaulting to wpilib.OpModeRobotBase.DEFAULT_PERIOD here: as of
        # this writing that constant is exposed as 20.0 - looks like a units
        # bug (20ms meant, not 20s) - so we just omit the argument entirely
        # and let the no-arg constructor overload apply its own (correct)
        # internal default instead of trusting that constant.
        if period is None:
            super().__init__()
        else:
            super().__init__(period)
        hal.report_usage("Framework", "CommandRobot")

    def _register(
        self,
        mode: hal.RobotMode,
        name: str,
        group: str,
        description: str,
        text_color: wpiutil.Color | None,
        background_color: wpiutil.Color | None,
    ) -> OpModeTriggers:
        opmode = OpModeTriggers(name)
        if text_color is None or background_color is None:
            self.add_opmode_factory(CommandOpMode, mode, name, group, description)
        else:
            self.add_opmode_factory(
                CommandOpMode,
                mode,
                name,
                group,
                description,
                text_color,
                background_color,
            )
        return opmode

    def create_auto_opmode(
        self,
        name: str,
        group: str = "",
        description: str = "",
        text_color: wpiutil.Color | None = None,
        background_color: wpiutil.Color | None = None,
    ) -> OpModeTriggers:
        """Creates and registers an autonomous opmode descriptor."""
        return self._register(
            hal.RobotMode.AUTONOMOUS,
            name,
            group,
            description,
            text_color,
            background_color,
        )

    def create_teleop_opmode(
        self,
        name: str,
        group: str = "",
        description: str = "",
        text_color: wpiutil.Color | None = None,
        background_color: wpiutil.Color | None = None,
    ) -> OpModeTriggers:
        """Creates and registers a teleoperated opmode descriptor."""
        return self._register(
            hal.RobotMode.TELEOPERATED,
            name,
            group,
            description,
            text_color,
            background_color,
        )

    def create_utility_opmode(
        self,
        name: str,
        group: str = "",
        description: str = "",
        text_color: wpiutil.Color | None = None,
        background_color: wpiutil.Color | None = None,
    ) -> OpModeTriggers:
        """Creates and registers a utility opmode descriptor."""
        return self._register(
            hal.RobotMode.UTILITY,
            name,
            group,
            description,
            text_color,
            background_color,
        )
