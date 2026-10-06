# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .command import Command
    from .coroutine import ForkResult

__all__ = ["CommandCancelled", "ForkFailed", "failing_command"]

#: Attribute the scheduler sets on an exception that escaped a command body.
#: Read it through :func:`failing_command` rather than by name.
_FAILING_COMMAND_ATTR = "commands3_failing_command"


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


class ForkFailed(CommandCancelled):
    """
    Raised at a ``fork()``/``await_()``/``all_of()``/``any_of()`` call site
    when at least one of the given commands couldn't be scheduled and the
    call was left to cancel on failure (the default).

    Because this is a ``CommandCancelled`` subclass, it unwinds the command
    and every ancestor it was forked from exactly the way an ordinary
    cancellation does, running ``try/finally`` cleanup on the way out; the
    scheduler then cancels the composition's root so every command in it
    runs its cancellation hooks. Pass ``cancel_on_failure=False`` to get a
    ``ForkResult`` back instead and handle the failure in the command body.

    :ivar result: the fork result describing which commands failed and why.
    """

    def __init__(self, result: ForkResult) -> None:
        self.result = result

        failures = ", ".join(
            f"{failure.command.name} ({type(failure).__name__})"
            for failure in result.failed_commands
        )
        super().__init__(f"Failed to fork: {failures}")


def failing_command(error: BaseException) -> Command | None:
    """
    The command whose body raised ``error``, if the scheduler attributed it.

    ``Scheduler.run()`` re-raises an exception thrown by a command body
    unchanged, so by the time it reaches the caller the execution context
    that knew which command was running has already unwound. The scheduler
    therefore records the responsible command on the exception itself before
    re-raising, which this reads back::

        try:
            Scheduler.get_default().run()
        except Exception as e:
            command = failing_command(e)
            if command is not None:
                print(f"{command.name} failed")
            raise

    Returns ``None`` for an exception the scheduler never attributed - one
    raised outside a command body, or re-raised after being caught inside
    one.
    """
    return getattr(error, _FAILING_COMMAND_ATTR, None)


def _attribute_to_command(
    error: BaseException, command: Command, root: Command | None
) -> None:
    """
    Record ``command`` as responsible for ``error`` and add a human-readable
    note naming it.

    Called by the scheduler on its error path, so this must never raise: an
    exception from annotating would mask the command's real failure. The
    first (innermost) attribution wins, so an exception that passes through
    more than one scheduler frame keeps the command that actually raised it.
    """
    try:
        if getattr(error, _FAILING_COMMAND_ATTR, None) is not None:
            return
        setattr(error, _FAILING_COMMAND_ATTR, command)

        note = f"Raised by commands3 command {command.name!r}"
        if root is not None and root is not command:
            note += f", running as part of {root.name!r} (now cancelled)"
        error.add_note(f"{note}.")
    except Exception:  # noqa: BLE001,S110 - deliberately broad and silent:
        # this runs on the scheduler's error path, so raising (or logging,
        # which can itself raise) would mask the command's real failure.
        # Losing the annotation is strictly better than losing `error`.
        pass
