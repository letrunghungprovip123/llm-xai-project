"""Chạy Decision Support Core từ các upstream outputs đã được duyệt."""

from __future__ import annotations

from .build import build_decision_outputs, write_decision_outputs
from .load import load_decision_inputs
from .validate import (
    print_validation_summary,
    validate_decision_outputs,
    write_validation_report,
)


def main() -> int:
    """Load → build → validate → write theo thứ tự dễ theo dõi."""

    input_data = load_decision_inputs()
    outputs = build_decision_outputs(input_data)
    validation_report = validate_decision_outputs(outputs, input_data)

    write_decision_outputs(outputs)
    write_validation_report(validation_report)
    print_validation_summary(validation_report, outputs)

    return 0 if validation_report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
