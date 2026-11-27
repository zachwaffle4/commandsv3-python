# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""The ``@command`` decorator on mechanism methods, other methods, and plain or nested functions."""

import pytest

from commands3 import Command, Mechanism, Scheduler, command, yield_


class Arm(Mechanism):
    @command
    async def lower(self, degrees: float = 45.0) -> None:
        self.lowered_to = degrees

    @command()
    async def with_parens(self) -> None:
        pass

    @command(name="Custom")
    async def named(self) -> None:
        pass


class Intake(Mechanism):
    @command
    async def grab(self) -> None:
        await yield_()


class Robot:
    def __init__(self) -> None:
        self.arm = Arm("Arm")
        self.intake = Intake("Intake")

    @command
    async def nothing(self) -> None:
        pass

    def score(self) -> Command:
        @command(requires=(self.intake, self.arm))
        async def body() -> None:
            await self.intake.grab()
            await self.arm.lower()

        return body()

    def named_score(self) -> Command:
        @command(name="Score!", requires=(self.intake, self.arm))
        async def body() -> None:
            pass

        return body()


_SHARED_ARM = Arm("Shared Arm")


@command
async def standalone(arm: Arm) -> None:
    pass


@command(requires=_SHARED_ARM)
async def uses_shared_arm() -> None:
    pass


@command(requires=[_SHARED_ARM, Intake("Shared Intake")])
async def uses_both() -> None:
    pass


def make_lower(arm: Arm) -> Command:
    @command(requires=arm)
    async def body() -> None:
        pass

    return body()


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


def test_mechanism_method_requires_its_mechanism_and_is_named_after_it():
    arm = Arm("Left Arm")

    lower = arm.lower()

    assert isinstance(lower, Command)
    assert lower.requirements == {arm}
    assert lower.name == "Left Arm.lower"


def test_two_instances_get_distinct_names():
    assert Arm("Left").lower().name == "Left.lower"
    assert Arm("Right").lower().name == "Right.lower"


def test_empty_parentheses_are_the_same_as_none():
    arm = Arm("Arm")

    with_parens = arm.with_parens()

    assert with_parens.requirements == {arm}
    assert with_parens.name == "Arm.with_parens"


def test_name_overrides_the_default():
    assert Arm("Arm").named().name == "Custom"


def test_each_call_builds_a_new_command():
    arm = Arm("Arm")

    assert arm.lower() is not arm.lower()


def test_arguments_are_passed_to_the_body(scheduler):
    arm = Arm("Arm")

    scheduler.schedule(arm.lower(10.0))
    scheduler.run()

    assert arm.lowered_to == 10.0


def test_keyword_arguments_are_passed_to_the_body(scheduler):
    arm = Arm("Arm")

    scheduler.schedule(arm.lower(degrees=20.0))
    scheduler.run()

    assert arm.lowered_to == 20.0


def test_mechanism_method_adds_extra_requirements_to_itself():
    class Elevator(Mechanism):
        @command(requires=_SHARED_ARM)
        async def handoff(self) -> None:
            pass

    elevator = Elevator("Elevator")
    handoff = elevator.handoff()

    assert handoff.requirements == {elevator, _SHARED_ARM}
    assert handoff.name == "Elevator.handoff"


def test_method_of_another_class_requires_nothing_by_default():
    nothing = Robot().nothing()

    assert nothing.requirements == frozenset()
    assert nothing.name == "Robot.nothing"


def test_nested_function_in_a_method_takes_the_methods_name():
    robot = Robot()

    score = robot.score()

    assert score.requirements == {robot.intake, robot.arm}
    assert score.name == "Robot.score"


def test_nested_function_can_still_be_named():
    assert Robot().named_score().name == "Score!"


def test_nested_function_in_a_plain_function_takes_its_name():
    arm = Arm("Arm")

    lower = make_lower(arm)

    assert lower.requirements == {arm}
    assert lower.name == "make_lower"


def test_nested_composition_runs(scheduler):
    robot = Robot()
    score = robot.score()

    scheduler.schedule(score)
    scheduler.run()
    assert scheduler.is_running(score)
    scheduler.run()

    assert not scheduler.is_running(score)
    assert robot.arm.lowered_to == 45.0


def test_method_of_a_class_defined_in_a_function_is_a_method():
    class Local(Mechanism):
        @command
        async def go(self) -> None:
            pass

    local = Local("Local")
    go = local.go()

    assert go.requirements == {local}
    assert go.name == "Local.go"


def test_plain_function_requires_nothing_and_uses_its_name():
    standalone_command = standalone(Arm("Arm"))

    assert standalone_command.requirements == frozenset()
    assert standalone_command.name == "standalone"


def test_plain_function_takes_a_single_mechanism():
    assert uses_shared_arm().requirements == {_SHARED_ARM}


def test_plain_function_takes_an_iterable_of_mechanisms():
    assert {m.name for m in uses_both().requirements} == {
        "Shared Arm",
        "Shared Intake",
    }


@pytest.mark.parametrize(
    ("argument", "hint"), [("Score", "name="), (Arm("Arm"), "requires=")]
)
def test_positional_options_are_rejected_with_a_hint(argument, hint):
    with pytest.raises(TypeError, match=f"`{hint}`"):
        command(argument)


def test_decorated_method_keeps_its_name_and_docstring():
    class Documented(Mechanism):
        @command
        async def documented(self) -> None:
            """Does a thing."""

    assert Documented.documented.__name__ == "documented"
    assert Documented.documented.__doc__ == "Does a thing."
