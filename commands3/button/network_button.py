# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

from __future__ import annotations

from typing import TYPE_CHECKING

import ntcore

from ..event_loop import EventLoop
from ..trigger import Trigger

if TYPE_CHECKING:
    from ..scheduler import Scheduler

__all__ = ["NetworkButton"]


class NetworkButton(Trigger):
    """
    A trigger that uses a NetworkTables boolean field. It is false whenever
    the NetworkTables instance isn't connected.

    Accepted forms:

    - ``NetworkButton(topic)`` with an ``ntcore.BooleanTopic``
    - ``NetworkButton(subscriber)`` with an ``ntcore.BooleanSubscriber``
    - ``NetworkButton(table, field)`` with an ``ntcore.NetworkTable``
    - ``NetworkButton("table_name", field)``, using the default instance, or
      the one passed as ``inst=``
    """

    def __init__(
        self,
        source: ntcore.BooleanTopic
        | ntcore.BooleanSubscriber
        | ntcore.NetworkTable
        | str,
        field: str | None = None,
        *,
        inst: ntcore.NetworkTableInstance | None = None,
        scheduler: Scheduler | None = None,
        loop: EventLoop | None = None,
    ) -> None:
        if source is None:
            raise ValueError("NetworkButton: source must not be None")

        if isinstance(source, str):
            if inst is None:
                inst = ntcore.NetworkTableInstance.get_default()
            source = inst.get_table(source)
        if isinstance(source, ntcore.NetworkTable):
            if field is None:
                raise ValueError("NetworkButton: a table needs a field name")
            source = source.get_boolean_topic(field)
        if isinstance(source, ntcore.BooleanTopic):
            source = source.subscribe(False)

        sub = source
        super().__init__(
            lambda: sub.get_topic().get_instance().is_connected() and sub.get(),
            scheduler,
            loop,
        )
