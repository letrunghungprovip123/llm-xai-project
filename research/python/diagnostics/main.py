"""Run Diagnostics & Mechanisms from approved upstream outputs."""

from __future__ import annotations

from .build import build_diagnostic_outputs, write_diagnostic_outputs
from .load import load_diagnostic_inputs
from .validate import (
    print_validation_summary,
    validate_diagnostic_outputs,
    write_validation_report,
)


def main() -> int:
    input_data = load_diagnostic_inputs()
    outputs = build_diagnostic_outputs(input_data)
    validation_report = validate_diagnostic_outputs(
        outputs,
        input_data,
    )

    write_diagnostic_outputs(outputs)
    write_validation_report(validation_report)
    print_validation_summary(validation_report, outputs)

    return 0 if validation_report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
