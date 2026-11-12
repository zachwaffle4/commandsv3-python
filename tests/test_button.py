# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

import ntcore
import pytest
import wpilib
from wpilib import simulation

from commands3 import (
    Command,
    CommandGamepad,
    CommandGenericHID,
    CommandJoystick,
    InternalButton,
    JoystickButton,
    Mechanism,
    NetworkButton,
    POVButton,
    Scheduler,
    Trigger,
    park,
)

PORT = 2


class DummyMechanism(Mechanism):
    pass


@pytest.fixture
def scheduler():
    return Scheduler.create_independent_scheduler()


@pytest.fixture(autouse=True)
def sim_timing():
    simulation.pause_timing()
    yield
    simulation.resume_timing()


@pytest.fixture
def hid_sim():
    sim = simulation.GenericHIDSim(PORT)
    sim.set_buttons_maximum_index(32)
    sim.set_axes_maximum_index(8)
    sim.set_povs_maximum_index(1)
    sim.notify_new_data()
    yield sim
    sim.set_raw_button(1, False)
    sim.set_raw_axis(0, 0.0)
    sim.set_pov(0, wpilib.POVDirection.CENTER)
    sim.notify_new_data()


def _press(sim, button, pressed=True):
    sim.set_raw_button(button, pressed)
    sim.notify_new_data()


def _command():
    async def body():
        await park()

    return Command.requiring(DummyMechanism()).executing(body).named("Parked")


# -- CommandGenericHID ------------------------------------------------------


def test_button_trigger_follows_the_raw_button(scheduler, hid_sim):
    hid = CommandGenericHID(PORT, scheduler)
    command = _command()
    hid.button(1).on_true(command)

    scheduler.run()
    assert not scheduler.is_running(command)

    _press(hid_sim, 1)
    scheduler.run()
    assert scheduler.is_running(command)


def test_button_triggers_are_cached_per_loop(scheduler, hid_sim):
    hid = CommandGenericHID(PORT, scheduler)
    other_loop = type(scheduler.get_default_event_loop())()

    assert hid.button(1) is hid.button(1)
    assert hid.button(1) is hid.button(1, scheduler.get_default_event_loop())
    assert hid.button(1) is not hid.button(2)
    assert hid.button(1) is not hid.button(1, other_loop)


def test_axis_triggers_are_cached_per_axis_and_threshold(scheduler, hid_sim):
    hid = CommandGenericHID(PORT, scheduler)

    assert hid.axis_greater_than(0, 0.5) is hid.axis_greater_than(0, 0.5)
    assert hid.axis_greater_than(0, 0.5) is not hid.axis_greater_than(0, 0.6)
    assert hid.axis_greater_than(0, 0.5) is not hid.axis_less_than(0, 0.5)
    assert hid.axis_greater_than(0, 0.5) is not hid.axis_magnitude_greater_than(0, 0.5)


def test_axis_triggers(scheduler, hid_sim):
    hid = CommandGenericHID(PORT, scheduler)
    greater = hid.axis_greater_than(0, 0.5)
    less = hid.axis_less_than(0, -0.5)
    magnitude = hid.axis_magnitude_greater_than(0, 0.5)

    hid_sim.set_raw_axis(0, 0.75)
    hid_sim.notify_new_data()
    scheduler.run()
    assert (greater.get_as_boolean(), less.get_as_boolean()) == (True, False)
    assert magnitude.get_as_boolean()

    hid_sim.set_raw_axis(0, -0.75)
    hid_sim.notify_new_data()
    scheduler.run()
    assert (greater.get_as_boolean(), less.get_as_boolean()) == (False, True)
    assert magnitude.get_as_boolean()

    hid_sim.set_raw_axis(0, 0.25)
    hid_sim.notify_new_data()
    scheduler.run()
    assert not greater.get_as_boolean()
    assert not less.get_as_boolean()
    assert not magnitude.get_as_boolean()


def test_pov_triggers(scheduler, hid_sim):
    hid = CommandGenericHID(PORT, scheduler)
    up = hid.pov_up()
    center = hid.pov_center()
    assert up is hid.pov(wpilib.POVDirection.UP)

    scheduler.run()
    assert center.get_as_boolean()
    assert not up.get_as_boolean()

    hid_sim.set_pov(0, wpilib.POVDirection.UP)
    hid_sim.notify_new_data()
    scheduler.run()
    assert up.get_as_boolean()
    assert not center.get_as_boolean()


def test_get_command_generic_hid_is_cached_per_scheduler_and_port(scheduler):
    other = Scheduler.create_independent_scheduler()

    hid = CommandGenericHID.get_command_generic_hid(PORT, scheduler)
    assert hid is CommandGenericHID.get_command_generic_hid(PORT, scheduler)
    assert hid is not CommandGenericHID.get_command_generic_hid(PORT + 1, scheduler)
    assert hid is not CommandGenericHID.get_command_generic_hid(PORT, other)
    assert hid.scheduler is scheduler


def test_get_command_generic_hid_rejects_out_of_range_ports(scheduler):
    with pytest.raises(RuntimeError):
        CommandGenericHID.get_command_generic_hid(99, scheduler)


def test_wraps_an_existing_generic_hid(scheduler, hid_sim):
    wrapped = wpilib.DriverStation.get_generic_hid(PORT)
    hid = CommandGenericHID(wrapped, scheduler)
    assert hid.get_hid() is wrapped


# -- CommandJoystick --------------------------------------------------------


def test_joystick_trigger_and_top(scheduler, hid_sim):
    joystick = CommandJoystick(PORT, scheduler)
    trigger = joystick.trigger()
    top = joystick.top()

    _press(hid_sim, wpilib.Joystick.ButtonType.TRIGGER_BUTTON.value)
    scheduler.run()
    assert trigger.get_as_boolean()
    assert not top.get_as_boolean()

    _press(hid_sim, wpilib.Joystick.ButtonType.TRIGGER_BUTTON.value, False)
    _press(hid_sim, wpilib.Joystick.ButtonType.TOP_BUTTON.value)
    scheduler.run()
    assert not trigger.get_as_boolean()
    assert top.get_as_boolean()


def test_joystick_axes_and_channels(scheduler, hid_sim):
    joystick = CommandJoystick(PORT, scheduler)
    assert joystick.get_hid() is CommandGenericHID.get_command_generic_hid(
        PORT, scheduler
    )

    joystick.set_x_channel(3)
    assert joystick.get_x_channel() == 3

    hid_sim.set_raw_axis(3, 0.5)
    hid_sim.notify_new_data()
    assert joystick.get_x() == pytest.approx(0.5)


# -- CommandGamepad ---------------------------------------------------------


def test_gamepad_buttons_use_gamepad_indices(scheduler, hid_sim):
    gamepad = CommandGamepad(PORT, scheduler)
    face_down = gamepad.face_down()
    touchpad = gamepad.touchpad()

    _press(hid_sim, wpilib.Gamepad.Button.FACE_DOWN.value)
    scheduler.run()
    assert face_down.get_as_boolean()
    assert not touchpad.get_as_boolean()

    _press(hid_sim, wpilib.Gamepad.Button.TOUCHPAD.value)
    scheduler.run()
    assert touchpad.get_as_boolean()

    _press(hid_sim, wpilib.Gamepad.Button.FACE_DOWN.value, False)
    _press(hid_sim, wpilib.Gamepad.Button.TOUCHPAD.value, False)


@pytest.mark.parametrize(
    "method, button",
    [
        (name.lower(), button)
        for name, button in [
            ("FACE_DOWN", wpilib.Gamepad.Button.FACE_DOWN),
            ("BACK", wpilib.Gamepad.Button.BACK),
            ("LEFT_BUMPER", wpilib.Gamepad.Button.LEFT_BUMPER),
            ("DPAD_RIGHT", wpilib.Gamepad.Button.DPAD_RIGHT),
            ("MISC_1", wpilib.Gamepad.Button.MISC_1),
            ("RIGHT_PADDLE_1", wpilib.Gamepad.Button.RIGHT_PADDLE_1),
            ("MISC_6", wpilib.Gamepad.Button.MISC_6),
        ]
    ],
)
def test_gamepad_button_methods_map_to_their_button(scheduler, method, button):
    gamepad = CommandGamepad(PORT, scheduler)
    # `misc_1` is spelled `misc1` etc. on the Python class.
    name = method.replace("misc_", "misc").replace("paddle_", "paddle")
    assert getattr(gamepad, name)() is gamepad.button(button.value)


def test_gamepad_trigger_axes(scheduler, hid_sim):
    gamepad = CommandGamepad(PORT, scheduler)
    left = gamepad.left_trigger()
    right = gamepad.right_trigger(0.9)
    assert left is gamepad.left_trigger(0.5)

    hid_sim.set_raw_axis(wpilib.Gamepad.Axis.LEFT_TRIGGER.value, 0.6)
    hid_sim.set_raw_axis(wpilib.Gamepad.Axis.RIGHT_TRIGGER.value, 0.6)
    hid_sim.notify_new_data()
    scheduler.run()
    assert left.get_as_boolean()
    assert not right.get_as_boolean()

    hid_sim.set_raw_axis(wpilib.Gamepad.Axis.LEFT_TRIGGER.value, 0.0)
    hid_sim.set_raw_axis(wpilib.Gamepad.Axis.RIGHT_TRIGGER.value, 0.0)
    hid_sim.notify_new_data()


def test_gamepad_can_wrap_an_existing_gamepad(scheduler):
    wrapped = wpilib.DriverStation.get_gamepad(PORT)
    gamepad = CommandGamepad(wrapped, scheduler)
    assert gamepad.get_gamepad() is wrapped
    assert gamepad.get_hid().get_hid() is wrapped.get_hid()


# -- InternalButton ---------------------------------------------------------


def test_internal_button_follows_set_pressed(scheduler):
    button = InternalButton(scheduler=scheduler)
    command = _command()
    button.on_true(command)

    scheduler.run()
    assert not scheduler.is_running(command)

    button.set_pressed(True)
    scheduler.run()
    assert scheduler.is_running(command)


def test_internal_button_inversion(scheduler):
    button = InternalButton(True, scheduler=scheduler)

    scheduler.run()
    assert button.get_as_boolean()

    button.set_pressed(True)
    scheduler.run()
    assert not button.get_as_boolean()

    button.set_inverted(False)
    scheduler.run()
    assert button.get_as_boolean()


# -- JoystickButton / POVButton --------------------------------------------


def test_joystick_button_reads_the_raw_button(scheduler, hid_sim):
    hid = wpilib.DriverStation.get_generic_hid(PORT)
    button = JoystickButton(hid, 4, scheduler=scheduler)

    scheduler.run()
    assert not button.get_as_boolean()

    _press(hid_sim, 4)
    scheduler.run()
    assert button.get_as_boolean()
    _press(hid_sim, 4, False)


def test_joystick_button_accepts_an_hid_device(scheduler, hid_sim):
    joystick = wpilib.Joystick(wpilib.DriverStation.get_generic_hid(PORT))
    button = JoystickButton(joystick, 4, scheduler=scheduler)

    _press(hid_sim, 4)
    scheduler.run()
    assert button.get_as_boolean()
    _press(hid_sim, 4, False)


def test_joystick_button_rejects_none(scheduler):
    with pytest.raises(ValueError):
        JoystickButton(None, 1, scheduler=scheduler)  # ty: ignore[invalid-argument-type]


def test_pov_button(scheduler, hid_sim):
    hid = wpilib.DriverStation.get_generic_hid(PORT)
    up = POVButton(hid, wpilib.POVDirection.UP, scheduler=scheduler)
    on_second_pov = POVButton(hid, wpilib.POVDirection.UP, 1, scheduler=scheduler)

    hid_sim.set_pov(0, wpilib.POVDirection.UP)
    hid_sim.notify_new_data()
    scheduler.run()
    assert up.get_as_boolean()
    assert not on_second_pov.get_as_boolean()


def test_pov_button_rejects_none(scheduler):
    with pytest.raises(ValueError):
        POVButton(None, wpilib.POVDirection.UP, scheduler=scheduler)  # ty: ignore[invalid-argument-type]


# -- NetworkButton ----------------------------------------------------------


@pytest.fixture
def nt_inst():
    inst = ntcore.NetworkTableInstance.create()
    yield inst
    ntcore.NetworkTableInstance.destroy(inst)


def test_network_button_is_false_while_disconnected(scheduler, nt_inst):
    publisher = nt_inst.get_boolean_topic("/buttons/go").publish()
    publisher.set(True)

    button = NetworkButton("buttons", "go", inst=nt_inst, scheduler=scheduler)
    scheduler.run()
    assert not nt_inst.is_connected()
    assert not button.get_as_boolean()


@pytest.mark.parametrize("form", ["topic", "table", "name"])
def test_network_button_construction_forms(scheduler, nt_inst, form):
    topic = nt_inst.get_boolean_topic("/buttons/go")
    sources = {
        "topic": lambda: NetworkButton(topic, scheduler=scheduler),
        "table": lambda: NetworkButton(
            nt_inst.get_table("buttons"), "go", scheduler=scheduler
        ),
        "name": lambda: NetworkButton(
            "buttons", "go", inst=nt_inst, scheduler=scheduler
        ),
    }
    assert isinstance(sources[form](), Trigger)


def test_network_button_table_requires_a_field(scheduler, nt_inst):
    with pytest.raises(ValueError):
        NetworkButton(nt_inst.get_table("buttons"), scheduler=scheduler)
