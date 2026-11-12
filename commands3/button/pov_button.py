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

__all__ = ["POVButton"]


class POVButton(Trigger):
    """A trigger that gets its state from a POV on a ``GenericHID``."""

    def __init__(
        self,
        joystick: wpilib.GenericHID | wpilib.HIDDevice,
        angle: wpilib.POVDirection,
        pov_number: int = 0,
        *,
        scheduler: Scheduler | None = None,
        loop: EventLoop | None = None,
    ) -> None:
        """
        :param joystick: The ``GenericHID`` (or ``HIDDevice``) that has the POV.
        :param angle: The desired angle.
        :param pov_number: The POV number; see ``GenericHID.get_pov``. Defaults to 0.
        """
        if joystick is None:
            raise ValueError("POVButton: joystick must not be None")
        hid = (
            joystick if isinstance(joystick, wpilib.GenericHID) else joystick.get_hid()
        )
        super().__init__(lambda: hid.get_pov(pov_number) == angle, scheduler, loop)
