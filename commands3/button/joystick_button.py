# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

from __future__ import annotations

from typing import TYPE_CHECKING

import wpilib

from ..event_loop import EventLoop
from ..trigger import Trigger

if TYPE_CHECKING:
    from ..scheduler import Scheduler

__all__ = ["JoystickButton"]


class JoystickButton(Trigger):
    """A trigger that gets its state from a ``GenericHID`` button."""

    def __init__(
        self,
        joystick: wpilib.GenericHID | wpilib.HIDDevice,
        button_number: int,
        *,
        scheduler: Scheduler | None = None,
        loop: EventLoop | None = None,
    ) -> None:
        """
        :param joystick: The ``GenericHID`` (or ``HIDDevice``, such as a
            ``Joystick``) that has the button.
        :param button_number: The button number; see
            ``GenericHID.get_raw_button``.
        """
        if joystick is None:
            raise ValueError("JoystickButton: joystick must not be None")
        hid = (
            joystick if isinstance(joystick, wpilib.GenericHID) else joystick.get_hid()
        )
        super().__init__(lambda: hid.get_raw_button(button_number), scheduler, loop)
