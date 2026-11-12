# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""``Trigger`` factories and ``Trigger`` subclasses for driver station input."""

from .command_dual_sense_controller import CommandDualSenseController
from .command_dual_sense_edge_controller import CommandDualSenseEdgeController
from .command_dual_shock4_controller import CommandDualShock4Controller
from .command_game_cube_controller import CommandGameCubeController
from .command_gamepad import CommandGamepad
from .command_generic_hid import CommandGenericHID
from .command_joystick import CommandJoystick
from .command_logitech_f310_controller import CommandLogitechF310Controller
from .command_steam_controller import CommandSteamController
from .command_switch2_gc_controller import CommandSwitch2GCController
from .command_switch2_pro_controller import CommandSwitch2ProController
from .command_switch_n64_controller import CommandSwitchN64Controller
from .command_switch_pro_controller import CommandSwitchProController
from .command_xbox_controller import CommandXboxController
from .internal_button import InternalButton
from .joystick_button import JoystickButton
from .network_button import NetworkButton
from .pov_button import POVButton

__all__ = [
    "CommandDualSenseController",
    "CommandDualSenseEdgeController",
    "CommandDualShock4Controller",
    "CommandGameCubeController",
    "CommandGamepad",
    "CommandGenericHID",
    "CommandJoystick",
    "CommandLogitechF310Controller",
    "CommandSteamController",
    "CommandSwitch2GCController",
    "CommandSwitch2ProController",
    "CommandSwitchN64Controller",
    "CommandSwitchProController",
    "CommandXboxController",
    "InternalButton",
    "JoystickButton",
    "NetworkButton",
    "POVButton",
]
