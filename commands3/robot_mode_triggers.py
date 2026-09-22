# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""``Trigger`` factories for running commands when the robot mode changes."""

from __future__ import annotations

import wpilib

from .trigger import Trigger

__all__ = ["autonomous", "disabled", "teleop", "utility"]


def autonomous() -> Trigger:
    """Returns a trigger that is true when the robot is enabled in autonomous mode."""
    return Trigger(wpilib.RobotState.is_autonomous_enabled)


def teleop() -> Trigger:
    """Returns a trigger that is true when the robot is enabled in teleop mode."""
    return Trigger(wpilib.RobotState.is_teleop_enabled)


def disabled() -> Trigger:
    """Returns a trigger that is true when the robot is disabled."""
    return Trigger(wpilib.RobotState.is_disabled)


def utility() -> Trigger:
    """Returns a trigger that is true when the robot is enabled in utility mode."""
    return Trigger(wpilib.RobotState.is_utility_enabled)
