from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pandas.errors import MergeError

from research.python.data_mart.build import (
    build_claims_table,
    build_data_mart,
    write_data_mart,
)
from research.python.data_mart.load import read_jsonl_file
from research.python.data_mart.validate import (
    validate_data_mart,
    write_validation_report,
)


EVIDENCE_LEVELS = ["S0", "S1", "S2", "S3", "S4", "S5"]
MODELS = ["model_a", "model_b"]
CASES = [
    {
        "case_id": "100",
        "stratum": "alpha",
        "true_label": 1,
        "predicted_class": 1,
        "probability": 0.8,
    },
    {
        "case_id": "200",
        "stratum": "beta",
        "true_label": 0,
        "predicted_class": 0,
        "probability": 0.2,
    },
]


def make_evidence_package(case: dict[str, object], level: str) -> dict[str, object]:
    feature_items: list[dict[str, object]] = []
    allowed_feature_ids: list[str] = []

    if level != "S0":
        feature_items = [
            {
                "feature_id": "feature_a",
                "feature_name": "feature_a",
                "display_name": "Feature A" if level != "S1" else None,
                "concept": "concept_a" if level in {"S2", "S3", "S4", "S5"} else None,
                "concept_display_name": "Concept A",
                "shap_value": 0.3,
                "abs_shap_value": 0.3,
                "direction": "increases_risk",
                "rank": 1,
                "strength": "strong",
                "safe_phrase": "Feature A increases predicted risk." if level != "S1" else None,
                "value": 1.0,
            }
        ]
        allowed_feature_ids = ["feature_a"]

    concept_items: list[dict[str, object]] = []
    allowed_concept_ids: list[str] = []
    if level in {"S4", "S5"}:
        concept_items = [
            {
                "concept": "concept_a",
                "concept_display_name": "Concept A",
                "direction": "increases_risk",
                "representative_feature": feature_items[0],
                "supporting_features": [],
                "selected_feature_ids": ["feature_a"],
                "feature_count": 1,
                "selected_abs_shap_sum": 0.3,
            }
        ]
        allowed_concept_ids = ["concept_a"]

    package_id = f"pkg_{level}_{case['case_id']}"
    return {
        "package_id": package_id,
        "source_ir_id": f"ir_{case['case_id']}",
        "source_evidence_id": f"evidence_{case['case_id']}",
        "trace_id": f"trace_{case['case_id']}",
        "run_mode": "evaluation",
        "ir_schema_version": "v2.0",
        "evidence_package_schema_version": "2.1",
        "evidence_level": level,
        "internal_metadata": {
            "customer": {
                "SK_ID_CURR": int(str(case["case_id"])),
                "row_index": int(str(case["case_id"])),
                "case_type": case["stratum"],
                "selection_rank": 1,
            },
            "ground_truth": {
                "has_ground_truth": True,
                "true_label": case["true_label"],
                "true_label_text": "high" if case["true_label"] == 1 else "low",
            },
        },
        "prediction": {
            "predicted_class": case["predicted_class"],
            "predicted_label": "high" if case["predicted_class"] == 1 else "low",
            "probability": case["probability"],
            "threshold": 0.5,
            "threshold_comparison": "above_or_equal_threshold" if case["probability"] >= 0.5 else "below_threshold",
            "is_above_threshold": case["probability"] >= 0.5,
        },
        "selected_evidence": feature_items,
        "concept_evidence": concept_items,
        "selection_metrics": {
            "selected_evidence_count": len(feature_items),
            "coverage": 0.7 if feature_items else None,
            "coverage_status": "PASSED" if feature_items else "NOT_APPLICABLE",
        },
        "narrative_policy": {
            "must_include_uncertainty": True,
        },
        "constraints": {
            "allowed_claim_ids": [],
            "allowed_feature_ids": allowed_feature_ids,
            "allowed_concept_ids": allowed_concept_ids,
            "forbidden_rule_ids": [],
            "claim_policy": {
                "allow_prediction_claim": True,
                "allow_uncertainty_claim": True,
                "allow_feature_claim": level != "S0",
                "allow_concept_claim": level in {"S4", "S5"},
            },
        },
        "audit_trace": {
            "selection_method": "fixture",
        },
        "backend_explanation_skeleton": (
            {"main_factor_slots": ["feature_a"], "required_section_order": ["prediction", "factors"]}
            if level == "S5"
            else None
        ),
    }


def make_generation(
    case: dict[str, object],
    model_id: str,
    level: str,
    model_order: int,
    case_order: int,
    usable: bool,
) -> dict[str, object]:
    package_id = f"pkg_{level}_{case['case_id']}"
    generation_id = f"generation_{model_id}_{case['case_id']}_{level}"
    return {
        "canonical_key": generation_id,
        "cohort_key": f"{case['case_id']}::{level}",
        "matrix_role": "main",
        "model_order": model_order,
        "case_order": case_order,
        "evidence_level_order": int(level[1:]),
        "generation_id": generation_id,
        "run_id": f"run_{model_id}",
        "experiment_stage": "evaluation",
        "model_id": model_id,
        "model_revision": "revision_1",
        "revision_status": "pinned",
        "case_id": case["case_id"],
        "source_ir_id": f"ir_{case['case_id']}",
        "evidence_level": level,
        "repeat_id": 1,
        "package_id": package_id,
        "source_evidence_id": f"evidence_{case['case_id']}",
        "prompt_id": f"prompt_{generation_id}",
        "prompt_version": "prompt_v1",
        "output_schema_version": "1.0",
        "input_package_sha256": "input_hash",
        "input_package_hash_verified": True,
        "prompt_message_sha256": "prompt_hash",
        "prompt_hash_verified": True,
        "runtime_status": "SUCCESS",
        "finish_reason": "stop" if usable else "length",
        "truncated_response": not usable,
        "raw_json_parse_success": usable,
        "schema_valid": usable,
        "usable": usable,
        "usability_reason_codes": [] if usable else ["truncated_response"],
        "generation_record": {
            "model_provider": "fixture_provider",
            "remote_model_id": model_id,
            "model_family": model_id,
            "decoding_config": {
                "temperature": 0.2,
                "top_p": 1.0,
                "max_tokens": 100,
                "frequency_penalty": 0,
                "presence_penalty": 0,
            },
            "output_constraint_mode": "json_schema",
            "case_metadata": {
                "customer_id": int(str(case["case_id"])),
                "selection_stratum": case["stratum"],
                "prediction_outcome": "TP" if case["true_label"] == 1 else "TN",
                "true_label": case["true_label"],
            },
            "runtime_metrics": {
                "latency_ms": 10,
                "retry_count": 0,
                "input_token_count": 20,
                "output_token_count": 10,
                "total_token_count": 30,
                "provider_api_cost_usd": 0,
                "truncated_response": not usable,
            },
            "schema_metrics": {
                "json_parse_success": usable,
                "missing_required_field_count": 0,
                "validation_error_count": 0 if usable else 1,
            },
            "parsed_output": (
                {
                    "prediction_summary": "Prediction summary",
                    "factors": [],
                    "uncertainty_note": "Uncertain",
                    "distributed_evidence_note": "",
                    "safe_summary": "Summary",
                }
                if usable
                else None
            ),
        },
    }


def make_fixture_input() -> dict[str, list[dict[str, object]]]:
    evidence_packages = [
        make_evidence_package(case, level)
        for case in CASES
        for level in EVIDENCE_LEVELS
    ]

    generations: list[dict[str, object]] = []
    claims: list[dict[str, object]] = []
    validations: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []

    unusable_generation_id = "generation_model_b_200_S5"

    for model_order, model_id in enumerate(MODELS, start=1):
        for case_order, case in enumerate(CASES, start=1):
            for level in EVIDENCE_LEVELS:
                generation_id = f"generation_{model_id}_{case['case_id']}_{level}"
                usable = generation_id != unusable_generation_id
                generations.append(
                    make_generation(
                        case,
                        model_id,
                        level,
                        model_order,
                        case_order,
                        usable,
                    )
                )

                if usable:
                    claim_id = f"claim_{generation_id}"
                    claims.append(
                        {
                            "local_claim_index": 1,
                            "source_section": "prediction_summary",
                            "source_text": "Prediction summary",
                            "source_span_start": 0,
                            "source_span_end": 18,
                            "claim_type": "prediction",
                            "claim_subtype": "OVERALL_LABEL",
                            "proposition_status": "COMPLETE",
                            "claim_id": claim_id,
                            "generation_id": generation_id,
                            "model_id": model_id,
                            "source_ir_id": f"ir_{case['case_id']}",
                            "case_id": case["case_id"],
                            "evidence_level": level,
                            "repeat_id": 1,
                        }
                    )
                    validations.append(
                        {
                            "validation_id": f"validation_{claim_id}",
                            "claim_id": claim_id,
                            "generation_id": generation_id,
                            "case_id": case["case_id"],
                            "model_id": model_id,
                            "evidence_level": level,
                            "repeat_id": 1,
                            "execution_status": "SUCCESS",
                            "validation_status": "SUPPORTED",
                            "evidence_status": "SUPPORTED",
                            "policy_status": "COMPLIANT",
                            "reason_code": "EXACT_MATCH",
                            "primary_reason_code": "EXACT_MATCH",
                            "reason_codes": ["EXACT_MATCH"],
                            "expected": {},
                            "observed": {},
                            "normalizations_applied": [],
                            "source_record_keys": [],
                            "unresolved_facts": [],
                            "numeric_comparison": None,
                            "error": None,
                        }
                    )

                summaries.append(
                    {
                        "generation_id": generation_id,
                        "case_id": case["case_id"],
                        "model_id": model_id,
                        "evidence_level": level,
                        "repeat_id": 1,
                        "usable": usable,
                        "total_claims": 1 if usable else 0,
                        "supported_count": 1 if usable else None,
                        "unsupported_count": 0 if usable else None,
                        "contradicted_count": 0 if usable else None,
                        "not_verifiable_count": 0 if usable else None,
                        "not_applicable_count": 0 if usable else None,
                    }
                )

    return {
        "evidence_packages": evidence_packages,
        "generation_index": generations,
        "final_claims": claims,
        "validation_results": validations,
        "generation_summaries": summaries,
    }


class DataMartTest(unittest.TestCase):
    def test_read_jsonl_reports_invalid_line(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            file_path = Path(temporary_dir) / "records.jsonl"
            file_path.write_text('{"id": 1}\nnot-json\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"records\.jsonl:2"):
                read_jsonl_file(file_path)

    def test_duplicate_validation_is_rejected(self) -> None:
        fixture = make_fixture_input()
        duplicate = dict(fixture["validation_results"][0])
        duplicate["validation_id"] = "duplicate_validation"

        with self.assertRaises(MergeError):
            build_claims_table(
                fixture["final_claims"],
                fixture["validation_results"] + [duplicate],
            )

    def test_unusable_generation_is_preserved_with_zero_claims(self) -> None:
        fixture = make_fixture_input()
        tables = build_data_mart(fixture)
        generations = tables["generations"]

        unusable = generations.loc[generations["usable"].eq(False)]
        self.assertEqual(len(unusable), 1)
        self.assertEqual(int(unusable.iloc[0]["claim_count"]), 0)
        self.assertEqual(len(generations), 24)

    def test_fixture_data_mart_passes_all_checks(self) -> None:
        fixture = make_fixture_input()
        tables = build_data_mart(fixture)
        expected_counts = {
            "cases": 2,
            "models": 2,
            "evidence_levels": 6,
            "evidence_packages": 12,
            "generations": 24,
            "usable_generations": 23,
            "unusable_generations": 1,
            "claims": 23,
            "validation_results": 23,
            "generation_summaries": 24,
        }
        expected_status_counts = {
            "SUPPORTED": 23,
        }
        expected_stratum_counts = {
            "alpha": 1,
            "beta": 1,
        }

        report = validate_data_mart(
            tables,
            fixture,
            expected_counts=expected_counts,
            expected_status_counts=expected_status_counts,
            expected_stratum_counts=expected_stratum_counts,
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["exit_gate"], "DATA_MART_READY")

    def test_claim_on_unusable_generation_fails_validation(self) -> None:
        fixture = make_fixture_input()
        unusable_generation_id = "generation_model_b_200_S5"
        extra_claim = dict(fixture["final_claims"][0])
        extra_claim["claim_id"] = "claim_on_unusable"
        extra_claim["generation_id"] = unusable_generation_id
        extra_claim["model_id"] = "model_b"
        extra_claim["case_id"] = "200"
        extra_claim["evidence_level"] = "S5"
        extra_validation = dict(fixture["validation_results"][0])
        extra_validation["validation_id"] = "validation_on_unusable"
        extra_validation["claim_id"] = "claim_on_unusable"
        extra_validation["generation_id"] = unusable_generation_id
        extra_validation["model_id"] = "model_b"
        extra_validation["case_id"] = "200"
        extra_validation["evidence_level"] = "S5"
        fixture["final_claims"].append(extra_claim)
        fixture["validation_results"].append(extra_validation)

        tables = build_data_mart(fixture)
        report = validate_data_mart(
            tables,
            fixture,
            expected_counts={
                "cases": 2,
                "models": 2,
                "evidence_levels": 6,
                "evidence_packages": 12,
                "generations": 24,
                "usable_generations": 23,
                "unusable_generations": 1,
                "claims": 24,
                "validation_results": 24,
                "generation_summaries": 24,
            },
            expected_status_counts={"SUPPORTED": 24},
            expected_stratum_counts={"alpha": 1, "beta": 1},
        )

        self.assertFalse(report["passed"])
        self.assertEqual(
            report["checks"]["claims_on_unusable_generations"]["observed"],
            1,
        )

    def test_outputs_are_written(self) -> None:
        fixture = make_fixture_input()
        tables = build_data_mart(fixture)
        report = validate_data_mart(
            tables,
            fixture,
            expected_counts={
                "cases": 2,
                "models": 2,
                "evidence_levels": 6,
                "evidence_packages": 12,
                "generations": 24,
                "usable_generations": 23,
                "unusable_generations": 1,
                "claims": 23,
                "validation_results": 23,
                "generation_summaries": 24,
            },
            expected_status_counts={"SUPPORTED": 23},
            expected_stratum_counts={"alpha": 1, "beta": 1},
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output_dir = Path(temporary_dir)
            write_data_mart(tables, output_dir)
            write_validation_report(report, output_dir)

            self.assertTrue((output_dir / "cases.csv").exists())
            self.assertTrue((output_dir / "generations.csv").exists())
            self.assertTrue((output_dir / "claims.csv").exists())
            validation = json.loads(
                (output_dir / "data_mart_validation.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(validation["passed"])


if __name__ == "__main__":
    unittest.main()
