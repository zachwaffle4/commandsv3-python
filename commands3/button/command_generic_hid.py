# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A ``GenericHID`` wrapper with ``Trigger`` factories."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wpilib

from ..event_loop import EventLoop
from ..trigger import Trigger

if TYPE_CHECKING:
    from ..scheduler import Scheduler

__all__ = ["CommandGenericHID"]

# Cache of triggers per scheduler and port
_hids: dict[Scheduler, dict[int, CommandGenericHID]] = {}


class CommandGenericHID:
    """A version of ``wpilib.GenericHID`` with ``Trigger`` factories for commands."""

    def __init__(
        self, hid: int | wpilib.GenericHID, scheduler: Scheduler | None = None
    ) -> None:
        """
        :param hid: The port index on the Driver Station that the device is
            plugged into, or the ``GenericHID`` object to wrap.
        :param scheduler: The scheduler that should execute the triggered
            commands. Defaults to the default scheduler.
        """
        if scheduler is None:
            from ..scheduler import Scheduler

            scheduler = Scheduler.get_default()
        if isinstance(hid, int):
            hid = wpilib.DriverStation.get_generic_hid(hid)

        self._scheduler = scheduler
        self._hid = hid
        self._button_cache: dict[EventLoop, dict[int, Trigger]] = {}
        self._axis_less_than_cache: dict[
            EventLoop, dict[tuple[int, float], Trigger]
        ] = {}
        self._axis_greater_than_cache: dict[
            EventLoop, dict[tuple[int, float], Trigger]
        ] = {}
        self._axis_magnitude_greater_than_cache: dict[
            EventLoop, dict[tuple[int, float], Trigger]
        ] = {}
        self._pov_cache: dict[
            EventLoop, dict[tuple[int, wpilib.POVDirection], Trigger]
        ] = {}

    @staticmethod
    def get_command_generic_hid(
        port: int, scheduler: Scheduler | None = None
    ) -> CommandGenericHID:
        """
        Gets the ``CommandGenericHID`` for the given scheduler and port. These
        objects are cached, so this always returns the same object for the same
        scheduler and port.

        :param port: The port index on the Driver Station that the device is
            plugged into.
        :param scheduler: The scheduler that should execute the triggered
            commands. Defaults to the default scheduler.
        """
        if scheduler is None:
            from ..scheduler import Scheduler

            scheduler = Scheduler.get_default()

        # Raises if the port is out of range, before anything is cached.
        wpilib.DriverStation.get_generic_hid(port)

        by_port = _hids.setdefault(scheduler, {})
        hid = by_port.get(port)
        if hid is None:
            hid = CommandGenericHID(port, scheduler)
            by_port[port] = hid
        return hid

    def get_hid(self) -> wpilib.GenericHID:
        """The underlying ``GenericHID`` object."""
        return self._hid

    @property
    def scheduler(self) -> Scheduler:
        """
        The scheduler that executes the triggered commands. Set in the
        constructor, defaulting to the default scheduler.
        """
        return self._scheduler

    def _loop_or_default(self, loop: EventLoop | None) -> EventLoop:
        return loop if loop is not None else self._scheduler.get_default_event_loop()

    # -- Buttons -----------------------------------------------------------

    def button(self, button: int, loop: EventLoop | None = None) -> Trigger:
        """
        Constructs a ``Trigger`` around this button's digital signal.

        :param button: The button index.
        :param loop: The event loop to attach the trigger to. Defaults to the
            scheduler's default event loop.
        """
        loop = self._loop_or_default(loop)
        cache = self._button_cache.setdefault(loop, {})
        trigger = cache.get(button)
        if trigger is None:
            trigger = Trigger(
                lambda: self._hid.get_raw_button(button), self._scheduler, loop
            )
            cache[button] = trigger
        return trigger

    # -- POVs --------------------------------------------------------------

    def pov(
        self,
        angle: wpilib.POVDirection,
        pov: int = 0,
        loop: EventLoop | None = None,
    ) -> Trigger:
        """
        Constructs a ``Trigger`` that is true when a POV on the HID is at the
        given angle.

        :param angle: The POV angle.
        :param pov: Index of the POV to read, starting at 0.
        :param loop: The event loop to attach the trigger to. Defaults to the
            scheduler's default event loop.
        """
        loop = self._loop_or_default(loop)
        cache = self._pov_cache.setdefault(loop, {})
        key = (pov, angle)
        trigger = cache.get(key)
        if trigger is None:
            trigger = Trigger(
                lambda: self._hid.get_pov(pov) == angle, self._scheduler, loop
            )
            cache[key] = trigger
        return trigger

    def pov_up(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger for the 0 degree angle (up) of the default (index 0) POV."""
        return self.pov(wpilib.POVDirection.UP, 0, loop)

    def pov_up_right(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger for the 45 degree angle (right up) of the default (index 0) POV."""
        return self.pov(wpilib.POVDirection.UP_RIGHT, 0, loop)

    def pov_right(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger for the 90 degree angle (right) of the default (index 0) POV."""
        return self.pov(wpilib.POVDirection.RIGHT, 0, loop)

    def pov_down_right(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger for the 135 degree angle (right down) of the default (index 0) POV."""
        return self.pov(wpilib.POVDirection.DOWN_RIGHT, 0, loop)

    def pov_down(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger for the 180 degree angle (down) of the default (index 0) POV."""
        return self.pov(wpilib.POVDirection.DOWN, 0, loop)

    def pov_down_left(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger for the 225 degree angle (down left) of the default (index 0) POV."""
        return self.pov(wpilib.POVDirection.DOWN_LEFT, 0, loop)

    def pov_left(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger for the 270 degree angle (left) of the default (index 0) POV."""
        return self.pov(wpilib.POVDirection.LEFT, 0, loop)

    def pov_up_left(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger for the 315 degree angle (left up) of the default (index 0) POV."""
        return self.pov(wpilib.POVDirection.UP_LEFT, 0, loop)

    def pov_center(self, loop: EventLoop | None = None) -> Trigger:
        """A trigger for the center (not pressed) position of the default (index 0) POV."""
        return self.pov(wpilib.POVDirection.CENTER, 0, loop)

    # -- Axes --------------------------------------------------------------

    def axis_less_than(
        self, axis: int, threshold: float, loop: EventLoop | None = None
    ) -> Trigger:
        """
        Constructs a ``Trigger`` that is true when the axis value is less than
        ``threshold``.

        :param axis: The axis to read, starting at 0.
        :param threshold: The value below which the trigger should be true.
        :param loop: The event loop to attach the trigger to. Defaults to the
            scheduler's default event loop.
        """
        return self._axis_trigger(
            self._axis_less_than_cache,
            axis,
            threshold,
            loop,
            lambda: self.get_raw_axis(axis) < threshold,
        )

    def axis_greater_than(
        self, axis: int, threshold: float, loop: EventLoop | None = None
    ) -> Trigger:
        """
        Constructs a ``Trigger`` that is true when the axis value is greater
        than ``threshold``.

        :param axis: The axis to read, starting at 0.
        :param threshold: The value above which the trigger should be true.
        :param loop: The event loop to attach the trigger to. Defaults to the
            scheduler's default event loop.
        """
        return self._axis_trigger(
            self._axis_greater_than_cache,
            axis,
            threshold,
            loop,
            lambda: self.get_raw_axis(axis) > threshold,
        )

    def axis_magnitude_greater_than(
        self, axis: int, threshold: float, loop: EventLoop | None = None
    ) -> Trigger:
        """
        Constructs a ``Trigger`` that is true when the magnitude of the axis
        value is greater than ``threshold``.

        :param axis: The axis to read, starting at 0.
        :param threshold: The value above which the trigger should be true.
        :param loop: The event loop to attach the trigger to. Defaults to the
            scheduler's default event loop.
        """
        return self._axis_trigger(
            self._axis_magnitude_greater_than_cache,
            axis,
            threshold,
            loop,
            lambda: abs(self.get_raw_axis(axis)) > threshold,
        )

    def _axis_trigger(
        self,
        caches: dict[EventLoop, dict[tuple[int, float], Trigger]],
        axis: int,
        threshold: float,
        loop: EventLoop | None,
        condition,
    ) -> Trigger:
        loop = self._loop_or_default(loop)
        cache = caches.setdefault(loop, {})
        key = (axis, threshold)
        trigger = cache.get(key)
        if trigger is None:
            trigger = Trigger(condition, self._scheduler, loop)
            cache[key] = trigger
        return trigger

    def get_raw_axis(self, axis: int) -> float:
        """The value of the axis, starting at 0."""
        return self._hid.get_raw_axis(axis)

    # -- Outputs and status ------------------------------------------------

    def set_rumble(self, type: wpilib.GenericHID.RumbleType, value: float) -> None:
        """
        Sets the rumble output for the HID.

        :param type: Which rumble value to set.
        :param value: The normalized value (0 to 1) to set the rumble to.
        """
        self._hid.set_rumble(type, value)

    def is_connected(self) -> bool:
        """True if the HID is connected."""
        return self._hid.is_connected()
