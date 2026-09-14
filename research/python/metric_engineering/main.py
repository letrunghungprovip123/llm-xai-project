"""Build and validate the materialized analytical metric table."""

from __future__ import annotations

from .build import build_metric_outputs, write_metric_outputs
from .load import load_metric_inputs
from .validate import (
    print_validation_summary,
    validate_metric_outputs,
    write_validation_report,
)


def main() -> int:
    input_data = load_metric_inputs()
    outputs = build_metric_outputs(input_data)
    validation_report = validate_metric_outputs(
        outputs,
        input_data,
    )

    write_metric_outputs(outputs)
    write_validation_report(validation_report)
    print_validation_summary(validation_report)

    return 0 if validation_report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
