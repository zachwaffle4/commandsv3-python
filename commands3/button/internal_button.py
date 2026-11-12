# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

from __future__ import annotations

from typing import TYPE_CHECKING

from ..event_loop import EventLoop
from ..trigger import Trigger

if TYPE_CHECKING:
    from ..scheduler import Scheduler

__all__ = ["InternalButton"]


class InternalButton(Trigger):
    """
    A trigger whose value the program sets manually, with an option to invert
    it.
    """

    def __init__(
        self,
        inverted: bool = False,
        *,
        scheduler: Scheduler | None = None,
        loop: EventLoop | None = None,
    ) -> None:
        """
        :param inverted: If false, the button is pressed when set to true;
            otherwise it is pressed when set to false.
        """
        # Set before the superclass constructor, which may poll-bind the
        # condition immediately.
        self._pressed = False
        self._inverted = inverted
        super().__init__(lambda: self._pressed != self._inverted, scheduler, loop)

    def set_inverted(self, inverted: bool) -> None:
        """Sets whether to invert the button state."""
        self._inverted = inverted

    def set_pressed(self, pressed: bool) -> None:
        """Sets whether the button is pressed."""
        self._pressed = pressed
