# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""The ``@command`` decorator, which turns a command's body into a factory for the command."""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable
from typing import Any, overload

from .command import Command, CommandBodyResult, StagedCommandBuilder
from .mechanism import Mechanism

__all__ = ["command"]


def _make_factory[**P](
    body: Callable[P, CommandBodyResult],
    name: str | None,
    requires: Mechanism | Iterable[Mechanism],
) -> Callable[P, Command]:
    function_name = getattr(body, "__name__", repr(body))
    fixed = (requires,) if isinstance(requires, Mechanism) else tuple(requires)

    # After the last "<locals>" (if any): "Arm.lower" is a method of Arm, and
    # a bare "body" is nested in a function. Robot.score.<locals>.body is
    # named after Robot.score. A module-level "score" is a plain function.
    qualname: str = getattr(body, "__qualname__", function_name)
    enclosing, nested, tail = qualname.rpartition(".<locals>.")
    in_class = "." in tail
    if nested and not in_class:
        function_name = enclosing.rpartition(".<locals>.")[2]

    @functools.wraps(body)
    def factory(*args: P.args, **kwargs: P.kwargs) -> Command:
        requirements = fixed
        default_name = function_name
        if in_class and args:
            instance = args[0]
            if isinstance(instance, Mechanism):
                requirements = (instance, *fixed)
                default_name = f"{instance.name}.{function_name}"
            else:
                default_name = f"{type(instance).__name__}.{function_name}"
        return (
            StagedCommandBuilder()
            .requiring_all(requirements)
            .executing(lambda: body(*args, **kwargs))
            .named(name or default_name)
        )

    return factory


@overload
def command[**P](body: Callable[P, CommandBodyResult], /) -> Callable[P, Command]: ...


@overload
def command[**P](
    *, name: str | None = None, requires: Mechanism | Iterable[Mechanism] = ()
) -> Callable[[Callable[P, CommandBodyResult]], Callable[P, Command]]: ...


def command(
    body: Callable[..., CommandBodyResult] | None = None,
    /,
    *,
    name: str | None = None,
    requires: Mechanism | Iterable[Mechanism] = (),
) -> Any:
    """
    Turns a function into a command factory: each call to the decorated
    function builds a new ``Command`` whose body is the original function,
    called with the same arguments.

    .. code-block:: python

        class Arm(Mechanism):
            @command  # requires the arm; named "Arm.raise_arm"
            async def raise_arm(self) -> None: ...

        class Robot(wpilib.OpModeRobot):
            def score(self) -> Command:
                @command(requires=(self.intake, self.arm))
                async def body() -> None:  # named "Robot.score"
                    await self.intake.grab()
                    await self.arm.raise_arm()

                return body()

    :param name: the command's name. Defaults to the function's name, after
        the mechanism's name for a ``Mechanism`` method or the class name for
        a method of any other class. A function nested in another is named
        after the one it's in, as ``body`` is above.
    :param requires: one mechanism or an iterable of them. A ``Mechanism``
        method always requires its own mechanism as well.

    Methods and nested functions are recognized by ``__qualname__``, so a
    ``@staticmethod`` in a class is mistaken for a method: put ``@command``
    on a module-level function instead.
    """
    if body is not None:
        if not callable(body):
            hint = "requires=" if isinstance(body, Mechanism) else "name="
            raise TypeError(f"@command takes its options as keywords: use `{hint}`")
        return _make_factory(body, name, requires)
    return lambda function: _make_factory(function, name, requires)
