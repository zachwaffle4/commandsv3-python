# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.


class CommandCancelled(BaseException):
    """
    Raised into a command's coroutine when the scheduler cancels it.

    Catching this without re-raising will prevent the command from actually
    stopping, since the scheduler relies on the exception propagating all
    the way out of the coroutine to consider it finished. Use ``try/finally``
    for cleanup that must run on cancellation instead of catching this
    directly.

    This is a subclass of ``BaseException`` rather than ``Exception`` -
    following the same convention as the built-in ``GeneratorExit`` - so
    that a broad ``except Exception:`` in a command body won't accidentally
    swallow cancellation and keep the command running.
    """
