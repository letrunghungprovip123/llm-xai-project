"""Validation gate for research-complete visualization marts v2."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import (
    EXPECTED_COUNTS,
    INVALID_GATE,
    OUTPUT_GATE,
    VISUALIZATION_VERSION,
)


def check(expected: object, observed: object, passed: bool) -> dict[str, object]:
    return {"expected": expected, "observed": observed, "passed": bool(passed)}


def validate_outputs(
    outputs: dict[str, pd.DataFrame],
    input_data: dict[str, Any],
) -> dict[str, Any]:
    checks: dict[str, dict[str, object]] = {}
    for name, expected_count in EXPECTED_COUNTS.items():
        checks[f"row_count_{name}"] = check(
            expected_count,
            len(outputs[name]),
            len(outputs[name]) == expected_count,
        )

    utilization = outputs["evidence_utilization_summary"]
    narrative = outputs["narrative_structure_summary"]
    heterogeneity = outputs["case_heterogeneity_summary"]
    rq_registry = outputs["research_question_registry"]
    pairs = outputs["llm_vs_template_case_pairs"]
    dictionary = outputs["visualization_dictionary"]
    report_numbers = outputs["certified_report_numbers"].set_index("metric_id")
    release_metadata = outputs["release_metadata"].iloc[0]
    dashboard_required = {
        dataset
        for page in input_data["dashboard_contract"]["pages"]
        for dataset in page["required_datasets"]
    }
    missing_dashboard_datasets = sorted(dashboard_required - set(outputs))
    all_text_values = "\n".join(
        value
        for frame in outputs.values()
        for value in (
            frame.select_dtypes(include=["object", "string"])
            .fillna("")
            .astype(str)
            .to_numpy()
            .ravel()
            .tolist()
        )
    )
    infinity_count = sum(
        int(
            np.isinf(
                frame.select_dtypes(include=["number"]).to_numpy(dtype=float)
            ).sum()
        )
        for frame in outputs.values()
    )

    checks.update(
        {
            "report_release_ready": check(
                "REPORT_WRITING_READY",
                input_data["report_readiness"].get("exit_gate"),
                input_data["report_readiness"].get("exit_gate")
                == "REPORT_WRITING_READY",
            ),
            "baseline_comparison_ready": check(
                "BASELINE_COMPARISON_READY",
                input_data["baseline_validation"].get("exit_gate"),
                input_data["baseline_validation"].get("exit_gate")
                == "BASELINE_COMPARISON_READY",
            ),
            "dashboard_contract_has_nine_pages": check(
                9,
                len(input_data["dashboard_contract"]["pages"]),
                len(input_data["dashboard_contract"]["pages"]) == 9,
            ),
            "dashboard_contract_parent_release_matches": check(
                "thesis-report-v1",
                input_data["dashboard_contract"].get("parent_analytical_release"),
                input_data["dashboard_contract"].get("parent_analytical_release")
                == "thesis-report-v1",
            ),
            "six_research_questions_unique": check(
                6,
                int(rq_registry["rq_id"].nunique()),
                rq_registry["rq_id"].nunique() == 6
                and not rq_registry["rq_id"].duplicated().any(),
            ),
            "rq6_activated_by_baseline_gate": check(
                "ACTIVE_AFTER_BASELINE_COMPARISON_READY",
                rq_registry.set_index("rq_id").loc["RQ6", "status"],
                rq_registry.set_index("rq_id").loc["RQ6", "status"]
                == "ACTIVE_AFTER_BASELINE_COMPARISON_READY",
            ),
            "utilization_generator_partition": check(
                {"LLM": 648, "TEMPLATE": 216},
                utilization["generator_family"].value_counts().to_dict(),
                utilization["generator_family"].value_counts().to_dict()
                == {"LLM": 648, "TEMPLATE": 216},
            ),
            "narrative_generator_partition": check(
                {"LLM": 648, "TEMPLATE": 216},
                narrative["generator_family"].value_counts().to_dict(),
                narrative["generator_family"].value_counts().to_dict()
                == {"LLM": 648, "TEMPLATE": 216},
            ),
            "heterogeneity_generator_partition": check(
                {"LLM": 648, "TEMPLATE": 216},
                heterogeneity["generator_family"].value_counts().to_dict(),
                heterogeneity["generator_family"].value_counts().to_dict()
                == {"LLM": 648, "TEMPLATE": 216},
            ),
            "primary_option_table_excludes_template": check(
                False,
                bool(
                    outputs["option_performance"]["model_id"]
                    .eq("template_baseline")
                    .any()
                ),
                not outputs["option_performance"]["model_id"]
                .eq("template_baseline")
                .any(),
            ),
            "decision_scenarios_exclude_template": check(
                False,
                bool(
                    outputs["scenario_options"]["option_id"]
                    .astype(str)
                    .str.contains("template", case=False)
                    .any()
                ),
                not outputs["scenario_options"]["option_id"]
                .astype(str)
                .str.contains("template", case=False)
                .any(),
            ),
            "template_pair_identity_unique": check(
                0,
                int(
                    pairs.duplicated(
                        ["case_id", "model_id", "evidence_level"]
                    ).sum()
                ),
                not pairs.duplicated(
                    ["case_id", "model_id", "evidence_level"]
                ).any(),
            ),
            "no_prediction_only_baseline_label": check(
                False,
                "Prediction-only baseline" in all_text_values,
                "Prediction-only baseline" not in all_text_values,
            ),
            "all_output_versions_are_v2": check(
                [VISUALIZATION_VERSION],
                sorted(
                    {
                        str(value)
                        for frame in outputs.values()
                        if "visualization_version" in frame.columns
                        for value in frame["visualization_version"].dropna().unique()
                    }
                ),
                all(
                    set(frame["visualization_version"].dropna().astype(str))
                    <= {VISUALIZATION_VERSION}
                    for frame in outputs.values()
                    if "visualization_version" in frame.columns
                ),
            ),
            "dictionary_covers_all_fields": check(
                sum(
                    len(frame.columns)
                    for name, frame in outputs.items()
                    if name != "visualization_dictionary"
                ),
                len(dictionary),
                len(dictionary)
                == sum(
                    len(frame.columns)
                    for name, frame in outputs.items()
                    if name != "visualization_dictionary"
                ),
            ),
            "metric_visibility_has_four_tiers": check(
                4,
                int(
                    outputs["metric_visibility_registry"][
                        "visibility_tier"
                    ].nunique()
                ),
                outputs["metric_visibility_registry"][
                    "visibility_tier"
                ].nunique()
                == 4,
            ),
            "dashboard_contract_datasets_present": check(
                [],
                missing_dashboard_datasets,
                not missing_dashboard_datasets,
            ),
            "parent_report_artifacts_verified": check(
                len(
                    input_data["report_manifest"].get(
                        "certified_report_files", []
                    )
                ),
                len(input_data["verified_report_paths"]),
                len(input_data["verified_report_paths"])
                == len(
                    input_data["report_manifest"].get(
                        "certified_report_files", []
                    )
                ),
            ),
            "baseline_output_artifacts_verified": check(
                len(
                    input_data["baseline_manifest"].get(
                        "output_artifacts", []
                    )
                ),
                len(input_data["verified_baseline_paths"]),
                len(input_data["verified_baseline_paths"])
                == len(
                    input_data["baseline_manifest"].get(
                        "output_artifacts", []
                    )
                ),
            ),
            "certified_denominator_parity": check(
                {
                    "planned": 648,
                    "usable": 638,
                    "unusable": 10,
                    "claims": 14667,
                },
                {
                    "planned": int(
                        report_numbers.loc["planned_llm_generations", "value"]
                    ),
                    "usable": int(
                        report_numbers.loc["usable_llm_generations", "value"]
                    ),
                    "unusable": int(
                        report_numbers.loc["unusable_llm_generations", "value"]
                    ),
                    "claims": int(
                        report_numbers.loc["final_atomic_claims", "value"]
                    ),
                },
                int(
                        report_numbers.loc["planned_llm_generations", "value"]
                    ) == 648
                and int(
                        report_numbers.loc["usable_llm_generations", "value"]
                    ) == 638
                and int(
                        report_numbers.loc["unusable_llm_generations", "value"]
                    ) == 10
                and int(
                        report_numbers.loc["final_atomic_claims", "value"]
                    ) == 14667,
            ),
            "release_metadata_commit_present": check(
                True,
                bool(str(release_metadata["parent_git_commit"]).strip()),
                bool(str(release_metadata["parent_git_commit"]).strip())
                and str(release_metadata["parent_git_commit"]).lower() != "nan",
            ),
            "primary_statistical_units_are_case_level": check(
                36,
                sorted(outputs["omnibus_tests"]["subject_count"].unique().tolist()),
                set(outputs["omnibus_tests"]["subject_count"]) == {36},
            ),
            "validator_sensitivity_units_are_case_level": check(
                36,
                sorted(
                    outputs["validator_sensitivity_tests"][
                        "paired_case_count"
                    ].unique().tolist()
                ),
                set(outputs["validator_sensitivity_tests"]["paired_case_count"]) == {36},
            ),
            "no_infinite_numeric_outputs": check(
                0,
                infinity_count,
                infinity_count == 0,
            ),
            "template_not_human_naturalness_evaluated": check(
                False,
                bool(
                    outputs["release_metadata"].iloc[0][
                        "human_naturalness_evaluated"
                    ]
                ),
                not bool(
                    outputs["release_metadata"].iloc[0][
                        "human_naturalness_evaluated"
                    ]
                ),
            ),
        }
    )
    failed = sum(not item["passed"] for item in checks.values())
    return {
        "schema_version": "visualization_validation_v2",
        "visualization_version": VISUALIZATION_VERSION,
        "check_count": len(checks),
        "failed_check_count": failed,
        "passed": failed == 0,
        "exit_gate": OUTPUT_GATE if failed == 0 else INVALID_GATE,
        "research_question_count": 6,
        "template_baseline_enabled": failed == 0,
        "template_is_fourth_llm": False,
        "claim_rows_used_as_independent_units": False,
        "checks": checks,
    }
