# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Checks the generated ``Command<Name>Controller`` classes against the schema
file they were generated from and against the robotpy controllers they wrap.
"""

import importlib.util
import json
from pathlib import Path

import pytest
import wpilib
from wpilib import simulation

import commands3.button
from commands3 import Scheduler

TOOLS = Path(__file__).resolve().parents[1] / "tools"
PORT = 3


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_hids", TOOLS / "generate_hids.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generate_hids = _load_generator()

with (TOOLS / "first_ds_hids.json").open(encoding="utf-8") as _f:
    CONTROLLERS = {entry["ClassName"]: entry for entry in json.load(_f)}


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


def _command_class(class_name):
    return getattr(commands3.button, f"Command{class_name}Controller")


def test_generated_files_are_up_to_date():
    # Regenerate with `uv run python tools/generate_hids.py`.
    assert generate_hids.main(["--check"]) == 0


def test_every_controller_in_the_schema_is_exported():
    for class_name in CONTROLLERS:
        assert f"Command{class_name}Controller" in commands3.button.__all__
        assert hasattr(commands3, f"Command{class_name}Controller")


@pytest.mark.parametrize("class_name", CONTROLLERS)
def test_buttons_are_bound_to_the_schema_indices(scheduler, class_name):
    controller = _command_class(class_name)(PORT, scheduler)
    hid = controller.get_hid()

    for name, index in CONTROLLERS[class_name]["buttons"].items():
        method = getattr(controller, generate_hids.snake_case(name))
        assert method() is hid.button(index), name


@pytest.mark.parametrize("class_name", CONTROLLERS)
def test_trigger_axes_are_bound_to_the_schema_indices(scheduler, class_name):
    controller = _command_class(class_name)(PORT, scheduler)
    hid = controller.get_hid()

    trigger_axes = {
        name: index
        for name, index in CONTROLLERS[class_name]["axes"].items()
        if generate_hids.is_trigger_axis(name)
    }
    assert trigger_axes, "every controller has two trigger axes"
    for name, index in trigger_axes.items():
        method = getattr(controller, generate_hids.snake_case(name))
        assert method(0.3) is hid.axis_greater_than(index, 0.3), name
        assert method() is hid.axis_greater_than(index, 0.5), name


@pytest.mark.parametrize("class_name", CONTROLLERS)
def test_axis_getters_read_the_wrapped_controller(scheduler, class_name):
    axes = CONTROLLERS[class_name]["axes"]
    sim = simulation.GenericHIDSim(PORT)
    sim.set_axes_maximum_index(max(axes.values()) + 1)
    # A distinct value per axis, so a getter wired to the wrong axis shows up.
    for name, index in axes.items():
        sim.set_raw_axis(index, 0.1 * (index + 1))
    sim.notify_new_data()

    try:
        controller = _command_class(class_name)(PORT, scheduler)
        wrapped = controller.get_controller()
        for name in axes:
            method = f"get_{generate_hids.snake_case(name)}"
            value = getattr(controller, method)()
            assert value == getattr(wrapped, method)(), name
            assert value != 0.0, name
    finally:
        for index in axes.values():
            sim.set_raw_axis(index, 0.0)
        sim.notify_new_data()


@pytest.mark.parametrize("class_name", CONTROLLERS)
def test_wraps_the_matching_wpilib_controller(scheduler, class_name):
    wpilib_class = getattr(wpilib, f"{class_name}Controller")

    from_port = _command_class(class_name)(PORT, scheduler)
    assert isinstance(from_port.get_controller(), wpilib_class)

    wrapped = wpilib_class(wpilib.DriverStation.get_generic_hid(PORT))
    from_object = _command_class(class_name)(wrapped, scheduler)
    assert from_object.get_controller() is wrapped


def test_a_controller_object_must_not_be_none(scheduler):
    with pytest.raises(ValueError):
        commands3.CommandXboxController(None, scheduler)  # ty: ignore[invalid-argument-type]


def test_name_conversions():
    assert generate_hids.snake_case("leftBumper") == "left_bumper"
    assert generate_hids.snake_case("CStickX") == "c_stick_x"
    assert generate_hids.snake_case("LTrigger") == "l_trigger"
    assert generate_hids.snake_case("ZAxis") == "z_axis"
    assert generate_hids.snake_case("rightPaddle1") == "right_paddle1"
    assert generate_hids.snake_case("PS") == "ps"
    assert generate_hids.constant_name("rightPaddle1") == "RIGHT_PADDLE_1"
    assert generate_hids.constant_name("L3") == "L3"
    assert generate_hids.constant_name("CStickX") == "C_STICK_X"
    assert generate_hids.display_name("rightPaddle1") == "Right Paddle 1"
    assert generate_hids.display_name("L3") == "L3"


def test_conflicting_method_names_are_rejected():
    entry = {
        "ClassName": "Fake",
        "buttons": {"leftTrigger": 0, "left_trigger": 1},
        "axes": {"leftTrigger": 0},
    }
    with pytest.raises(ValueError, match="conflicting"):
        generate_hids.normalize_controller(entry)


def test_reserved_method_names_are_rejected():
    entry = {"ClassName": "Fake", "buttons": {"button": 0}, "axes": {}}
    with pytest.raises(ValueError, match="conflicting"):
        generate_hids.normalize_controller(entry)
