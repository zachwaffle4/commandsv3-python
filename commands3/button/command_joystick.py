# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A ``Joystick`` wrapper with ``Trigger`` factories."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wpilib

from ..event_loop import EventLoop
from ..trigger import Trigger
from .command_generic_hid import CommandGenericHID

if TYPE_CHECKING:
    from ..scheduler import Scheduler

__all__ = ["CommandJoystick"]


class CommandJoystick:
    """A version of ``wpilib.Joystick`` with ``Trigger`` factories for commands."""

    def __init__(self, port: int, scheduler: Scheduler | None = None) -> None:
        """
        :param port: The port index on the Driver Station that the joystick is
            plugged into.
        :param scheduler: The scheduler that should execute the triggered
            commands. Defaults to the default scheduler.
        """
        self._hid = CommandGenericHID.get_command_generic_hid(port, scheduler)
        self._joystick = wpilib.Joystick(wpilib.DriverStation.get_generic_hid(port))

    def get_hid(self) -> CommandGenericHID:
        """The underlying ``CommandGenericHID`` object."""
        return self._hid

    def get_joystick(self) -> wpilib.Joystick:
        """The underlying ``wpilib.Joystick`` object."""
        return self._joystick

    # -- Buttons -----------------------------------------------------------

    def trigger(self, loop: EventLoop | None = None) -> Trigger:
        """
        Constructs a ``Trigger`` around the trigger button's digital signal.

        :param loop: The event loop to attach the trigger to. Defaults to the
            scheduler's default event loop.
        """
        return self._hid.button(wpilib.Joystick.ButtonType.TRIGGER_BUTTON.value, loop)

    def top(self, loop: EventLoop | None = None) -> Trigger:
        """
        Constructs a ``Trigger`` around the top button's digital signal.

        :param loop: The event loop to attach the trigger to. Defaults to the
            scheduler's default event loop.
        """
        return self._hid.button(wpilib.Joystick.ButtonType.TOP_BUTTON.value, loop)

    # -- Axis channels -----------------------------------------------------

    def set_x_channel(self, channel: int) -> None:
        """Sets the channel associated with the X axis."""
        self._joystick.set_x_channel(channel)

    def set_y_channel(self, channel: int) -> None:
        """Sets the channel associated with the Y axis."""
        self._joystick.set_y_channel(channel)

    def set_z_channel(self, channel: int) -> None:
        """Sets the channel associated with the Z axis."""
        self._joystick.set_z_channel(channel)

    def set_throttle_channel(self, channel: int) -> None:
        """Sets the channel associated with the throttle axis."""
        self._joystick.set_throttle_channel(channel)

    def set_twist_channel(self, channel: int) -> None:
        """Sets the channel associated with the twist axis."""
        self._joystick.set_twist_channel(channel)

    def get_x_channel(self) -> int:
        """The channel currently associated with the X axis."""
        return self._joystick.get_x_channel()

    def get_y_channel(self) -> int:
        """The channel currently associated with the Y axis."""
        return self._joystick.get_y_channel()

    def get_z_channel(self) -> int:
        """The channel currently associated with the Z axis."""
        return self._joystick.get_z_channel()

    def get_twist_channel(self) -> int:
        """The channel currently associated with the twist axis."""
        return self._joystick.get_twist_channel()

    def get_throttle_channel(self) -> int:
        """The channel currently associated with the throttle axis."""
        return self._joystick.get_throttle_channel()

    # -- Axis values -------------------------------------------------------

    def get_x(self) -> float:
        """
        The x position of the HID. Depends on the mapping of the joystick
        connected to the port; on most joysticks, positive is to the right.
        """
        return self._joystick.get_x()

    def get_y(self) -> float:
        """
        The y position of the HID. Depends on the mapping of the joystick
        connected to the port; on most joysticks, positive is to the back.
        """
        return self._joystick.get_y()

    def get_z(self) -> float:
        """The z position of the HID."""
        return self._joystick.get_z()

    def get_twist(self) -> float:
        """
        The twist value of the joystick. Depends on the mapping of the
        joystick connected to the port.
        """
        return self._joystick.get_twist()

    def get_throttle(self) -> float:
        """
        The throttle value of the joystick. Depends on the mapping of the
        joystick connected to the port.
        """
        return self._joystick.get_throttle()

    def get_magnitude(self) -> float:
        """The magnitude of the vector formed by the joystick's position relative to its origin."""
        return self._joystick.get_magnitude()

    def get_direction_radians(self) -> float:
        """
        The direction of the vector formed by the joystick and its origin, in
        radians. 0 is forward and clockwise is positive (straight right is
        pi/2).
        """
        return self._joystick.get_direction_radians()

    def get_direction_degrees(self) -> float:
        """
        The direction of the vector formed by the joystick and its origin, in
        degrees. 0 is forward and clockwise is positive (straight right is 90).
        """
        return self._joystick.get_direction_degrees()
