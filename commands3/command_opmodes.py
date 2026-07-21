# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Functions for registering command-based opmodes without subclassing
``CommandRobot``.

Prefer ``CommandRobot``'s instance methods over these when subclassing
``CommandRobot`` - they integrate opmode registration with the robot's
lifecycle via ``add_opmode_factory()``, whereas these functions only
register with ``wpilib.RobotState``.
"""

from __future__ import annotations

import hal
import wpilib
import wpiutil

from .opmode_triggers import OpModeTriggers

__all__ = ["create_auto_opmode", "create_teleop_opmode", "create_utility_opmode"]


def _register(
    mode: hal.RobotMode,
    name: str,
    group: str,
    description: str,
    text_color: wpiutil.Color | None,
    background_color: wpiutil.Color | None,
) -> OpModeTriggers:
    if text_color is None or background_color is None:
        wpilib.RobotState.add_opmode(mode, name, group, description)
    else:
        wpilib.RobotState.add_opmode(
            mode, name, group, description, text_color, background_color
        )
    return OpModeTriggers(name)


def create_auto_opmode(
    name: str,
    group: str = "",
    description: str = "",
    text_color: wpiutil.Color | None = None,
    background_color: wpiutil.Color | None = None,
) -> OpModeTriggers:
    """
    Creates and registers an autonomous opmode descriptor. Call
    ``wpilib.RobotState.publish_opmodes()`` after registration so newly added
    opmodes are visible to the Driver Station.
    """
    return _register(
        hal.RobotMode.AUTONOMOUS, name, group, description, text_color, background_color
    )


def create_teleop_opmode(
    name: str,
    group: str = "",
    description: str = "",
    text_color: wpiutil.Color | None = None,
    background_color: wpiutil.Color | None = None,
) -> OpModeTriggers:
    """
    Creates and registers a teleoperated opmode descriptor. Call
    ``wpilib.RobotState.publish_opmodes()`` after registration so newly added
    opmodes are visible to the Driver Station.
    """
    return _register(
        hal.RobotMode.TELEOPERATED,
        name,
        group,
        description,
        text_color,
        background_color,
    )


def create_utility_opmode(
    name: str,
    group: str = "",
    description: str = "",
    text_color: wpiutil.Color | None = None,
    background_color: wpiutil.Color | None = None,
) -> OpModeTriggers:
    """
    Creates and registers a utility opmode descriptor. Call
    ``wpilib.RobotState.publish_opmodes()`` after registration so newly added
    opmodes are visible to the Driver Station.
    """
    return _register(
        hal.RobotMode.UTILITY, name, group, description, text_color, background_color
    )
