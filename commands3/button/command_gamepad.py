# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A ``Gamepad`` wrapper with ``Trigger`` factories."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wpilib

from ..event_loop import EventLoop
from ..trigger import Trigger
from .command_generic_hid import CommandGenericHID

if TYPE_CHECKING:
    from ..scheduler import Scheduler

__all__ = ["CommandGamepad"]

_Button = wpilib.Gamepad.Button
_Axis = wpilib.Gamepad.Axis


class CommandGamepad:
    """
    A version of ``wpilib.Gamepad`` with ``Trigger`` factories for commands.

    Every button method takes an optional event loop to attach the trigger
    to, defaulting to the scheduler's default event loop. The returned
    triggers are cached per loop, so asking for the same button twice gives
    the same trigger.
    """

    def __init__(
        self, gamepad: int | wpilib.Gamepad, scheduler: Scheduler | None = None
    ) -> None:
        """
        :param gamepad: The port index on the Driver Station that the
            controller is plugged into, or the ``Gamepad`` object to wrap.
        :param scheduler: The scheduler that should execute the triggered
            commands. Defaults to the default scheduler.
        """
        if isinstance(gamepad, int):
            self._hid = CommandGenericHID.get_command_generic_hid(gamepad, scheduler)
            self._gamepad = wpilib.DriverStation.get_gamepad(gamepad)
        else:
            if gamepad is None:
                raise ValueError("Provided gamepad cannot be None")
            self._gamepad = gamepad
            self._hid = CommandGenericHID(gamepad.get_hid(), scheduler)

    def get_hid(self) -> CommandGenericHID:
        """The underlying ``CommandGenericHID`` object."""
        return self._hid

    def get_gamepad(self) -> wpilib.Gamepad:
        """The underlying ``wpilib.Gamepad`` object."""
        return self._gamepad

    def button(self, button: int, loop: EventLoop | None = None) -> Trigger:
        """
        Constructs a ``Trigger`` around this button's digital signal.

        :param button: The button index.
        :param loop: The event loop to attach the trigger to.
        """
        return self._hid.button(button, loop)

    # -- Buttons -----------------------------------------------------------

    def face_down(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Face Down button's digital signal."""
        return self.button(_Button.FACE_DOWN.value, loop)

    def face_right(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Face Right button's digital signal."""
        return self.button(_Button.FACE_RIGHT.value, loop)

    def face_left(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Face Left button's digital signal."""
        return self.button(_Button.FACE_LEFT.value, loop)

    def face_up(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Face Up button's digital signal."""
        return self.button(_Button.FACE_UP.value, loop)

    def back(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Back button's digital signal."""
        return self.button(_Button.BACK.value, loop)

    def guide(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Guide button's digital signal."""
        return self.button(_Button.GUIDE.value, loop)

    def start(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Start button's digital signal."""
        return self.button(_Button.START.value, loop)

    def left_stick(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Left Stick button's digital signal."""
        return self.button(_Button.LEFT_STICK.value, loop)

    def right_stick(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Right Stick button's digital signal."""
        return self.button(_Button.RIGHT_STICK.value, loop)

    def left_bumper(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Left Bumper button's digital signal."""
        return self.button(_Button.LEFT_BUMPER.value, loop)

    def right_bumper(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Right Bumper button's digital signal."""
        return self.button(_Button.RIGHT_BUMPER.value, loop)

    def dpad_up(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the D-Pad Up button's digital signal."""
        return self.button(_Button.DPAD_UP.value, loop)

    def dpad_down(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the D-Pad Down button's digital signal."""
        return self.button(_Button.DPAD_DOWN.value, loop)

    def dpad_left(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the D-Pad Left button's digital signal."""
        return self.button(_Button.DPAD_LEFT.value, loop)

    def dpad_right(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the D-Pad Right button's digital signal."""
        return self.button(_Button.DPAD_RIGHT.value, loop)

    def misc1(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Miscellaneous 1 button's digital signal."""
        return self.button(_Button.MISC_1.value, loop)

    def right_paddle1(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Right Paddle 1 button's digital signal."""
        return self.button(_Button.RIGHT_PADDLE_1.value, loop)

    def left_paddle1(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Left Paddle 1 button's digital signal."""
        return self.button(_Button.LEFT_PADDLE_1.value, loop)

    def right_paddle2(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Right Paddle 2 button's digital signal."""
        return self.button(_Button.RIGHT_PADDLE_2.value, loop)

    def left_paddle2(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Left Paddle 2 button's digital signal."""
        return self.button(_Button.LEFT_PADDLE_2.value, loop)

    def touchpad(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Touchpad button's digital signal."""
        return self.button(_Button.TOUCHPAD.value, loop)

    def misc2(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Miscellaneous 2 button's digital signal."""
        return self.button(_Button.MISC_2.value, loop)

    def misc3(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Miscellaneous 3 button's digital signal."""
        return self.button(_Button.MISC_3.value, loop)

    def misc4(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Miscellaneous 4 button's digital signal."""
        return self.button(_Button.MISC_4.value, loop)

    def misc5(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Miscellaneous 5 button's digital signal."""
        return self.button(_Button.MISC_5.value, loop)

    def misc6(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger around the Miscellaneous 6 button's digital signal."""
        return self.button(_Button.MISC_6.value, loop)

    # -- Trigger axes ------------------------------------------------------

    def left_trigger(
        self, threshold: float = 0.5, loop: EventLoop | None = None
    ) -> Trigger:
        """
        A trigger that is true when the left trigger's axis exceeds
        ``threshold``.

        :param threshold: The minimum axis value for the returned trigger to
            be true, in [0, 1] where 0 is the unpressed state of the axis.
        :param loop: The event loop to attach the trigger to.
        """
        return self._hid.axis_greater_than(_Axis.LEFT_TRIGGER.value, threshold, loop)

    def right_trigger(
        self, threshold: float = 0.5, loop: EventLoop | None = None
    ) -> Trigger:
        """
        A trigger that is true when the right trigger's axis exceeds
        ``threshold``.

        :param threshold: The minimum axis value for the returned trigger to
            be true, in [0, 1] where 0 is the unpressed state of the axis.
        :param loop: The event loop to attach the trigger to.
        """
        return self._hid.axis_greater_than(_Axis.RIGHT_TRIGGER.value, threshold, loop)

    # -- Axis values -------------------------------------------------------

    def get_left_x(self) -> float:
        """The X axis value of the left side of the controller. Right is positive."""
        return self._gamepad.get_left_x()

    def get_left_y(self) -> float:
        """The Y axis value of the left side of the controller. Back is positive."""
        return self._gamepad.get_left_y()

    def get_right_x(self) -> float:
        """The X axis value of the right side of the controller. Right is positive."""
        return self._gamepad.get_right_x()

    def get_right_y(self) -> float:
        """The Y axis value of the right side of the controller. Back is positive."""
        return self._gamepad.get_right_y()

    def get_left_trigger(self) -> float:
        """The left trigger value, bound to [0, 1] rather than the usual [-1, 1]."""
        return self._gamepad.get_left_trigger()

    def get_right_trigger(self) -> float:
        """The right trigger value, bound to [0, 1] rather than the usual [-1, 1]."""
        return self._gamepad.get_right_trigger()
