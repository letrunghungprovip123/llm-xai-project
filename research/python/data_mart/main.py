"""Build and validate the Batch 12 analytical data mart."""

from __future__ import annotations

from .build import build_data_mart, write_data_mart
from .config import OUTPUT_DIR
from .load import load_input_data
from .validate import (
    print_validation_summary,
    validate_data_mart,
    write_validation_report,
)


def main() -> int:
    input_data = load_input_data()
    tables = build_data_mart(input_data)
    validation_report = validate_data_mart(tables, input_data)

    write_data_mart(tables, OUTPUT_DIR)
    write_validation_report(validation_report, OUTPUT_DIR)
    print_validation_summary(validation_report)

    return 0 if validation_report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
