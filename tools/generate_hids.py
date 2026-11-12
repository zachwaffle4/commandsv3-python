# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""
Generates ``commands3/button/command_<name>_controller.py`` for every
controller in ``tools/first_ds_hids.json``.

Run from the repository root::

    uv run python tools/generate_hids.py           # rewrite the files
    uv run python tools/generate_hids.py --check   # fail if any are stale

The output is passed through ``ruff format`` so it matches the rest of the
package, which means the generated files are only reproducible with the
repository's pinned ruff. Jinja2 and ruff are both dev dependencies; the
generated files are committed, so nothing here is needed at runtime.
"""

from __future__ import annotations

import argparse
import json
import keyword
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

TOOLS_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = TOOLS_DIRECTORY.parent

TEMPLATE_NAME = "command_hid.py.jinja"

# Names the template defines on every generated class; a controller's own
# buttons and axes must not collide with them.
_RESERVED_METHODS = frozenset({"button", "get_hid", "get_controller"})

# Trigger axes that don't end in "Trigger".
_NAMED_TRIGGER_AXES = frozenset({"L2", "R2", "ZL", "ZR"})


def snake_case(name: str) -> str:
    """
    ``leftBumper`` -> ``left_bumper``, ``CStickX`` -> ``c_stick_x``,
    ``rightPaddle1`` -> ``right_paddle1``, ``PS`` -> ``ps``. Digits stay
    attached to the word before them, matching how robotpy names methods.
    """
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return name.lower()


def constant_name(name: str) -> str:
    """
    ``leftBumper`` -> ``LEFT_BUMPER``, ``rightPaddle1`` -> ``RIGHT_PADDLE_1``,
    ``L3`` -> ``L3``. The name of the controller's ``Button``/``Axis`` enum
    member.
    """
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"([a-z])([0-9])", r"\1_\2", name)
    return name.upper()


def display_name(name: str) -> str:
    """``leftBumper`` -> ``Left Bumper``, ``rightPaddle1`` -> ``Right Paddle 1``."""
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", name)
    name = re.sub(r"([a-z])([0-9])", r"\1 \2", name)
    return name[0].upper() + name[1:]


def is_trigger_axis(name: str) -> bool:
    return name.endswith("Trigger") or name in _NAMED_TRIGGER_AXES


def _entries(mapping: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "method": snake_case(name),
            "constant": constant_name(name),
            "doc": display_name(name),
            "value": value,
        }
        for name, value in mapping.items()
    ]


def normalize_controller(controller: dict[str, Any]) -> dict[str, Any]:
    """Turns one entry of the schema file into the template's variables."""
    buttons = _entries(controller["buttons"])
    axes = _entries(controller["axes"])
    trigger_axes = [axis for axis in axes if is_trigger_axis(axis["name"])]

    class_name = controller["ClassName"]

    # Every method the generated class will define, so a schema entry that
    # would shadow another (or a Python keyword) fails here instead of
    # producing a class that silently drops a binding.
    names = (
        sorted(_RESERVED_METHODS)
        + [e["method"] for e in buttons]
        + [e["method"] for e in trigger_axes]
        + [f"get_{e['method']}" for e in axes]
    )
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"{class_name}: conflicting method names {duplicates}")
    keywords = [name for name in names if keyword.iskeyword(name)]
    if keywords:
        raise ValueError(f"{class_name}: method names are keywords {keywords}")

    return {
        "class_name": class_name,
        "module_name": f"command_{snake_case(class_name)}_controller",
        "buttons": buttons,
        "axes": axes,
        "trigger_axes": trigger_axes,
    }


def format_with_ruff(source: str, filename: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--stdin-filename", filename, "-"],
        input=source,
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ruff format failed for {filename}:\n{result.stderr}")
    return result.stdout


def render_all(schema_file: Path, output_directory: Path) -> dict[Path, str]:
    """Renders every controller, returning ``{output path: formatted source}``."""
    with schema_file.open(encoding="utf-8") as f:
        controllers = [normalize_controller(c) for c in json.load(f)]

    env = Environment(
        loader=FileSystemLoader(TOOLS_DIRECTORY / "templates"),
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(TEMPLATE_NAME)

    rendered: dict[Path, str] = {}
    for controller in controllers:
        path = output_directory / f"{controller['module_name']}.py"
        rendered[path] = format_with_ruff(template.render(controller), path.name)
    return rendered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--schema-file",
        type=Path,
        default=TOOLS_DIRECTORY / "first_ds_hids.json",
        help="the controller definitions (default: tools/first_ds_hids.json)",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=REPOSITORY_ROOT / "commands3" / "button",
        help="where to write the modules (default: commands3/button)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if any generated file is missing or stale",
    )
    args = parser.parse_args(argv)

    rendered = render_all(args.schema_file, args.output_directory)

    if args.check:
        stale = [
            path
            for path, source in rendered.items()
            if not path.exists() or path.read_text(encoding="utf-8") != source
        ]
        for path in stale:
            print(f"stale: {path}", file=sys.stderr)
        return 1 if stale else 0

    for path, source in rendered.items():
        path.write_text(source, encoding="utf-8")
        print(f"wrote {path.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
