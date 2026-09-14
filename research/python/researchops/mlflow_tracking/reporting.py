from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


def write_json_report(path: Path, payload: Mapping[str, Any]) -> Path:
    """Write a machine report atomically and durably.

    Human-oriented stdout/stderr from MLflow is intentionally not parsed as a
    machine contract. Commands write one canonical JSON document to an explicit
    report path, then may print the same payload for interactive use.
    """

    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory_descriptor = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target


def emit_json_report(
    payload: Mapping[str, Any],
    *,
    report_path: str | Path | None = None,
) -> None:
    normalized = dict(payload)
    if report_path is not None:
        write_json_report(Path(report_path), normalized)
    print(
        json.dumps(
            normalized,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
