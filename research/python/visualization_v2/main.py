"""CLI for visualization presentation marts v2."""

from __future__ import annotations

from .build import (
    build_manifest,
    build_outputs,
    write_json,
    write_outputs,
)
from .config import MANIFEST_PATH, VALIDATION_PATH
from .load import load_visualization_v2_inputs
from .validate import validate_outputs


def main() -> int:
    input_data = load_visualization_v2_inputs()
    outputs = build_outputs(input_data)
    validation = validate_outputs(outputs, input_data)
    write_outputs(outputs)
    write_json(VALIDATION_PATH, validation)
    manifest = build_manifest(outputs, input_data)
    write_json(MANIFEST_PATH, manifest)
    print("Visualization presentation marts v2")
    print(f"- Research questions: {validation['research_question_count']}")
    print(f"- Datasets: {len(outputs)}")
    print(f"- Checks: {validation['check_count']}")
    print(f"- Failed: {validation['failed_check_count']}")
    print(f"- Exit gate: {validation['exit_gate']}")
    return 0 if validation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
