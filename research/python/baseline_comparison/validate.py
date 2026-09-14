"""Validation gate for the Template Baseline analytical layer."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import (
    EXPECTED_BASELINE_GENERATIONS,
    EXPECTED_CASES,
    EXPECTED_EVIDENCE_LEVELS,
    EXPECTED_LLM_GENERATIONS,
    EXPECTED_PAIRS,
    EXPECTED_SUMMARY_ROWS,
    INVALID_GATE,
    OUTPUT_GATE,
    TEST_METRICS,
)


def check(expected: object, observed: object, passed: bool) -> dict[str, object]:
    return {"expected": expected, "observed": observed, "passed": bool(passed)}


def validate_outputs(
    outputs: dict[str, pd.DataFrame],
    input_data: dict[str, Any],
) -> dict[str, Any]:
    claims = outputs["baseline_claims"]
    metrics = outputs["baseline_generation_metrics"]
    options = outputs["baseline_option_performance"]
    pairs = outputs["llm_vs_template_case_pairs"]
    summary = outputs["llm_vs_template_summary"]
    tests = outputs["llm_vs_template_tests"]

    expected_tests = (
        len(TEST_METRICS)
        * (
            3 * EXPECTED_EVIDENCE_LEVELS
            + 3
        )
    )
    finite_frames = [metrics, options, pairs, summary, tests]
    infinity_count = sum(
        int(
            np.isinf(
                frame.select_dtypes(include=["number"]).to_numpy(dtype=float)
            ).sum()
        )
        for frame in finite_frames
    )
    applicable = claims.loc[claims["is_applicable"].astype(bool)]
    status_partition = (
        applicable[
            [
                "is_supported",
                "is_not_verifiable",
                "is_unsupported",
                "is_contradicted",
            ]
        ]
        .astype(int)
        .sum(axis=1)
    )
    checks = {
        "parent_report_release_ready": check(
            "REPORT_WRITING_READY",
            input_data["report_readiness"].get("exit_gate"),
            input_data["report_readiness"].get("exit_gate") == "REPORT_WRITING_READY",
        ),
        "parent_report_manifest_artifacts_verified": check(
            len(input_data["report_manifest"].get("certified_report_files", [])),
            len(input_data["verified_report_paths"]),
            len(input_data["verified_report_paths"])
            == len(input_data["report_manifest"].get("certified_report_files", [])),
        ),
        "template_generation_count": check(
            EXPECTED_BASELINE_GENERATIONS,
            len(metrics),
            len(metrics) == EXPECTED_BASELINE_GENERATIONS,
        ),
        "template_generation_identity_unique": check(
            0,
            int(metrics["generation_id"].duplicated().sum()),
            not metrics["generation_id"].duplicated().any(),
        ),
        "template_case_evidence_unique": check(
            0,
            int(metrics.duplicated(["case_id", "evidence_level"]).sum()),
            not metrics.duplicated(["case_id", "evidence_level"]).any(),
        ),
        "template_case_count": check(
            EXPECTED_CASES,
            int(metrics["case_id"].nunique()),
            metrics["case_id"].nunique() == EXPECTED_CASES,
        ),
        "template_evidence_count": check(
            EXPECTED_EVIDENCE_LEVELS,
            int(metrics["evidence_level"].nunique()),
            metrics["evidence_level"].nunique() == EXPECTED_EVIDENCE_LEVELS,
        ),
        "template_all_usable": check(
            EXPECTED_BASELINE_GENERATIONS,
            int(metrics["usable"].sum()),
            metrics["usable"].astype(bool).all(),
        ),
        "template_claim_ids_unique": check(
            0,
            int(claims["claim_id"].duplicated().sum()),
            not claims["claim_id"].duplicated().any(),
        ),
        "applicable_claim_status_partition": check(
            [1],
            sorted(status_partition.unique().tolist()),
            set(status_partition.unique()) == {1},
        ),
        "metric_identity_e2e_equals_conservative_for_usable": check(
            0.0,
            float(
                np.nanmax(
                    np.abs(
                        metrics["end_to_end_faithfulness_yield"]
                        - metrics["conservative_faithfulness"]
                    )
                )
            ),
            np.allclose(
                metrics["end_to_end_faithfulness_yield"],
                metrics["conservative_faithfulness"],
                atol=1e-12,
                rtol=0.0,
                equal_nan=True,
            ),
        ),
        "baseline_option_count": check(
            EXPECTED_EVIDENCE_LEVELS,
            len(options),
            len(options) == EXPECTED_EVIDENCE_LEVELS,
        ),
        "llm_parent_generation_count": check(
            EXPECTED_LLM_GENERATIONS,
            len(input_data["llm_generation_metrics"]),
            len(input_data["llm_generation_metrics"]) == EXPECTED_LLM_GENERATIONS,
        ),
        "llm_template_pair_count": check(
            EXPECTED_PAIRS,
            len(pairs),
            len(pairs) == EXPECTED_PAIRS,
        ),
        "llm_template_pair_unique": check(
            0,
            int(pairs.duplicated(["case_id", "model_id", "evidence_level"]).sum()),
            not pairs.duplicated(["case_id", "model_id", "evidence_level"]).any(),
        ),
        "summary_row_count": check(
            EXPECTED_SUMMARY_ROWS,
            len(summary),
            len(summary) == EXPECTED_SUMMARY_ROWS,
        ),
        "test_row_count": check(
            expected_tests,
            len(tests),
            len(tests) == expected_tests,
        ),
        "all_tests_use_case_level_pairing": check(
            "1-36 paired canonical cases with planned and excluded counts",
            {
                "minimum": int(tests["paired_case_count"].min()),
                "maximum": int(tests["paired_case_count"].max()),
                "planned": sorted(tests["planned_pair_count"].unique().tolist()),
            },
            tests["paired_case_count"].between(1, EXPECTED_CASES).all()
            and set(tests["planned_pair_count"]) == {EXPECTED_CASES}
            and (
                tests["paired_case_count"] + tests["excluded_pair_count"]
                == EXPECTED_CASES
            ).all(),
        ),
        "primary_e2e_tests_use_all_36_cases": check(
            [EXPECTED_CASES],
            sorted(
                tests.loc[
                    tests["metric_id"] == "end_to_end_faithfulness_yield",
                    "paired_case_count",
                ].unique().tolist()
            ),
            set(
                tests.loc[
                    tests["metric_id"] == "end_to_end_faithfulness_yield",
                    "paired_case_count",
                ]
            ) == {EXPECTED_CASES},
        ),
        "holm_adjusted_p_values_bounded": check(
            True,
            bool(tests["adjusted_p_value"].between(0.0, 1.0).all()),
            tests["adjusted_p_value"].between(0.0, 1.0).all(),
        ),
        "template_excluded_from_decision_ranking": check(
            True,
            bool((~options["eligible_for_llm_decision_ranking"].astype(bool)).all()),
            (~options["eligible_for_llm_decision_ranking"].astype(bool)).all(),
        ),
        "no_infinite_numeric_outputs": check(
            0,
            infinity_count,
            infinity_count == 0,
        ),
    }
    failed = sum(not value["passed"] for value in checks.values())
    return {
        "schema_version": "baseline_comparison_validation_v1",
        "check_count": len(checks),
        "failed_check_count": failed,
        "passed": failed == 0,
        "exit_gate": OUTPUT_GATE if failed == 0 else INVALID_GATE,
        "template_baseline_denominator": EXPECTED_BASELINE_GENERATIONS,
        "llm_denominator_unchanged": EXPECTED_LLM_GENERATIONS,
        "template_is_fourth_llm": False,
        "claim_extraction_channel_identical_to_llm": False,
        "structured_template_adapter_limitation": True,
        "human_naturalness_evaluated": False,
        "claim_rows_used_as_independent_units": False,
        "checks": checks,
    }
