"""Run the Statistical Analysis Core from the approved analytical mart."""

from __future__ import annotations

from .build import (
    build_statistical_outputs,
    write_statistical_outputs,
)
from .load import load_statistical_inputs
from .validate import (
    print_validation_summary,
    validate_statistical_outputs,
    write_validation_report,
)


def main() -> int:
    input_data = load_statistical_inputs()
    outputs = build_statistical_outputs(input_data)
    validation_report = validate_statistical_outputs(
        outputs,
        input_data,
    )

    write_statistical_outputs(outputs)
    write_validation_report(validation_report)
    print_validation_summary(validation_report, outputs)

    return 0 if validation_report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
