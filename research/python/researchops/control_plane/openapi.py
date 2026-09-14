from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from research.python.researchops.contracts.io import canonical_json_bytes, project_root

from .app import create_app
from .settings import ControlPlaneSettings


OPENAPI_PATH = Path("config/platform/generated/researchops_openapi_v1.json")
LOCK_PATH = Path("config/platform/generated/researchops_openapi_v1.lock.sha256")


def schema_payload() -> dict:
    settings = ControlPlaneSettings(auth_mode="local", docs_enabled=True)
    return create_app(settings=settings).openapi()


def write_openapi(root: Path | None = None) -> tuple[Path, Path]:
    resolved = (root or project_root()).resolve()
    payload = schema_payload()
    target = resolved / OPENAPI_PATH
    lock = resolved / LOCK_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    lock.write_text(digest + "  " + OPENAPI_PATH.as_posix() + "\n", encoding="utf-8")
    return target, lock


def openapi_is_current(root: Path | None = None) -> bool:
    resolved = (root or project_root()).resolve()
    target = resolved / OPENAPI_PATH
    lock = resolved / LOCK_PATH
    if not target.is_file() or not lock.is_file():
        return False
    stored = json.loads(target.read_text(encoding="utf-8"))
    expected = schema_payload()
    if stored != expected:
        return False
    digest = hashlib.sha256(canonical_json_bytes(expected)).hexdigest()
    return lock.read_text(encoding="utf-8").split()[0] == digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="researchops-control-plane-openapi")
    parser.add_argument("command", choices=("compile", "check"))
    args = parser.parse_args(argv)
    if args.command == "compile":
        target, lock = write_openapi()
        print(f"OPENAPI_PATH={target}")
        print(f"OPENAPI_LOCK={lock}")
        return 0
    passed = openapi_is_current()
    print(f"RESEARCHOPS_OPENAPI_LOCK_CURRENT={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
