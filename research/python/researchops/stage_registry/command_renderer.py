"""Render and structurally resolve stage commands without executing them."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .models import RuntimeSpec, StageDefinition


@dataclass(frozen=True)
class CommandResolution:
    stage_id: str
    rendered: tuple[str, ...]
    structurally_valid: bool
    executable_available: bool
    details: tuple[str, ...]


def render_command(runtime: RuntimeSpec) -> tuple[str, ...]:
    return (runtime.executable, *runtime.args)


def _python_module_exists(root: Path, module_name: str) -> bool:
    relative = Path(*module_name.split("."))
    return (root / relative.with_suffix(".py")).is_file() or (
        root / relative / "__main__.py"
    ).is_file()


def _dispatcher_stages(root: Path) -> set[str]:
    text = (root / "research/ts/cli.ts").read_text(encoding="utf-8")
    return set(re.findall(r'^\s+"([^"]+)":\s*\{', text, flags=re.MULTILINE))


def resolve_command(
    stage: StageDefinition,
    root: Path,
) -> CommandResolution:
    runtime = stage.runtime
    details: list[str] = []
    valid = True
    working_directory = root / runtime.working_directory
    if not working_directory.is_dir():
        valid = False
        details.append(f"working directory does not exist: {runtime.working_directory}")

    if runtime.type == "python":
        args = list(runtime.args)
        if len(args) < 2 or args[0] != "-m":
            valid = False
            details.append("python command must start with -m <module>")
        elif not _python_module_exists(root, args[1]):
            valid = False
            details.append(f"python module does not exist: {args[1]}")
    elif runtime.type == "npm":
        package_path = root / "package.json"
        if not package_path.is_file():
            valid = False
            details.append("package.json is missing")
        else:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            scripts = package.get("scripts", {})
            if list(runtime.args[:3]) != ["run", "research", "--"]:
                valid = False
                details.append("npm command must invoke `npm run research -- <stage>`")
            elif "research" not in scripts:
                valid = False
                details.append("package.json does not define the research script")
            if stage.legacy_dispatcher_stage is None:
                valid = False
                details.append("npm dispatcher command lacks legacy_dispatcher_stage")
            elif stage.legacy_dispatcher_stage not in _dispatcher_stages(root):
                valid = False
                details.append(
                    f"dispatcher stage is missing: {stage.legacy_dispatcher_stage}"
                )
            elif len(runtime.args) != 4 or runtime.args[3] != stage.legacy_dispatcher_stage:
                valid = False
                details.append("npm command does not match legacy_dispatcher_stage")

    executable_available = shutil.which(runtime.executable) is not None
    if valid:
        details.append("command structure resolved")
    if not executable_available:
        details.append(f"executable not currently on PATH: {runtime.executable}")
    return CommandResolution(
        stage_id=stage.id,
        rendered=render_command(runtime),
        structurally_valid=valid,
        executable_available=executable_available,
        details=tuple(details),
    )
