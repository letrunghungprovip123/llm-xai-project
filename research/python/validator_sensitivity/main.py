"""Run Candidate-versus-V4 sensitivity without changing the primary release."""

from __future__ import annotations

import json

import numpy as np

from .build import build_outputs, read_jsonl
from .config import (
    CANDIDATE_SUMMARY_PATH,
    EXPECTED_CASES,
    EXPECTED_GENERATIONS,
    OUTPUT_DIR,
    PAIR_OUTPUT_PATH,
    SUMMARY_OUTPUT_PATH,
    TEST_OUTPUT_PATH,
    V4_SUMMARY_PATH,
    VALIDATION_OUTPUT_PATH,
)


def validate_outputs(outputs):
    pairs = outputs["pairs"]
    tests = outputs["tests"]
    checks = {
        "pair_count": {
            "expected": EXPECTED_GENERATIONS,
            "observed": len(pairs),
            "passed": len(pairs) == EXPECTED_GENERATIONS,
        },
        "generation_identity_unique": {
            "expected": 0,
            "observed": int(pairs["generation_id"].duplicated().sum()),
            "passed": not pairs["generation_id"].duplicated().any(),
        },
        "case_count": {
            "expected": EXPECTED_CASES,
            "observed": int(pairs["case_id"].nunique()),
            "passed": pairs["case_id"].nunique() == EXPECTED_CASES,
        },
        "all_tests_use_36_cases": {
            "expected": [EXPECTED_CASES],
            "observed": sorted(tests["paired_case_count"].unique().tolist()),
            "passed": set(tests["paired_case_count"]) == {EXPECTED_CASES},
        },
        "finite_test_values": {
            "expected": 0,
            "observed": int(
                np.isinf(
                    tests.select_dtypes(include=["number"]).to_numpy()
                ).sum()
            ),
            "passed": not np.isinf(
                tests.select_dtypes(include=["number"]).to_numpy()
            ).any(),
        },
    }
    failed = sum(not value["passed"] for value in checks.values())
    return {
        "schema_version": "validator_sensitivity_validation_v1",
        "primary_validator": "candidate",
        "sensitivity_validator": "v4",
        "claim_rows_used_as_independent_units": False,
        "check_count": len(checks),
        "failed_check_count": failed,
        "passed": failed == 0,
        "exit_gate": (
            "VALIDATOR_SENSITIVITY_READY"
            if failed == 0
            else "VALIDATOR_SENSITIVITY_INVALID"
        ),
        "checks": checks,
    }


def main() -> int:
    outputs = build_outputs(
        read_jsonl(CANDIDATE_SUMMARY_PATH),
        read_jsonl(V4_SUMMARY_PATH),
    )
    validation = validate_outputs(outputs)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs["pairs"].to_csv(PAIR_OUTPUT_PATH, index=False)
    outputs["summary"].to_csv(SUMMARY_OUTPUT_PATH, index=False)
    outputs["tests"].to_csv(TEST_OUTPUT_PATH, index=False)
    VALIDATION_OUTPUT_PATH.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print("Validator sensitivity")
    print(f"- Generation pairs: {len(outputs['pairs'])}")
    print(f"- Case-level tests: {len(outputs['tests'])}")
    print(f"- Exit gate: {validation['exit_gate']}")
    return 0 if validation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
