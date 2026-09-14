"""Load the frozen JSONL inputs used by the analytical data mart."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.python.common.research_release import (
    load_claim_measurement_release,
    verify_official_release_artifacts,
)

from .config import INPUT_PATHS


JsonRecord = dict[str, Any]
InputData = dict[str, list[JsonRecord]]


def check_input_file(file_path: Path) -> None:
    """Fail early when a configured input path is missing or not a file."""

    if not file_path.exists():
        raise FileNotFoundError(f"Required input does not exist: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"Required input is not a file: {file_path}")


def read_jsonl_file(file_path: Path) -> list[JsonRecord]:
    """Read a JSONL file and report the exact line of malformed input."""

    check_input_file(file_path)
    records: list[JsonRecord] = []

    with file_path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped_line = line.strip()

            if not stripped_line:
                continue

            try:
                record = json.loads(stripped_line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSONL record at {file_path}:{line_number}"
                ) from error

            if not isinstance(record, dict):
                raise ValueError(
                    "Expected a JSON object at "
                    f"{file_path}:{line_number}, got {type(record).__name__}"
                )

            records.append(record)

    if not records:
        raise ValueError(f"Required input is empty: {file_path}")

    return records


def load_input_data(
    input_paths: dict[str, Path] | None = None,
) -> InputData:
    """Load every configured Batch 12 input into memory.

    The current cohort is intentionally small enough for a simple in-memory
    implementation: 648 generations and 14,667 claims.  Keeping loading
    explicit makes the pipeline easier to read and debug.
    """

    if input_paths is None:
        release = load_claim_measurement_release()
        verify_official_release_artifacts(release)
        paths = INPUT_PATHS
    else:
        paths = input_paths

    input_data: InputData = {}

    for input_name, file_path in paths.items():
        input_data[input_name] = read_jsonl_file(file_path)

    return input_data
