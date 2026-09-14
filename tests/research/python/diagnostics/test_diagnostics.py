"""Tests for claim and generation mechanism diagnostics."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from research.python.common.paths import DEFAULT_PATHS, find_project_root
from research.python.diagnostics import build as build_module
from research.python.diagnostics import validate as validate_module
from research.python.diagnostics.build import (
    build_diagnostic_outputs,
    write_diagnostic_outputs,
)
from research.python.diagnostics.claim_diagnostics import (
    build_claim_base_frame,
    require_known_statuses,
)
from research.python.diagnostics.config import (
    HIGH_OVERLAP_THRESHOLD,
    OUTPUT_GATE,
)
from research.python.diagnostics.generation_diagnostics import (
    calculate_loss_components,
)
from research.python.diagnostics.load import (
    load_diagnostic_inputs,
    require_gate,
)
from research.python.diagnostics.safe_phrase import (
    best_match_sort_key,
    eligible_phrases_for_claim,
    evaluate_text_pair,
    extract_safe_phrase_items,
    match_claims_to_safe_phrases,
)
from research.python.diagnostics.summarize import (
    build_claim_mechanism_summary,
    build_generation_mechanism_summary,
    classify_failure,
    divide_or_nan,
)
from research.python.diagnostics.validate import (
    validate_diagnostic_outputs,
    write_validation_report,
)


class DiagnosticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.real_inputs = load_diagnostic_inputs()
        cls.real_outputs = build_diagnostic_outputs(cls.real_inputs)
        cls.safe_phrases = extract_safe_phrase_items(cls.real_inputs)

    def test_data_mart_gate_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "DATA_MART_READY"):
            require_gate(
                {
                    "passed": False,
                    "failed_check_count": 1,
                    "exit_gate": "DATA_MART_INVALID",
                },
                "DATA_MART_READY",
                "Data Mart",
            )

    def test_metric_gate_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "ANALYTICAL_MART_READY"):
            require_gate(
                {
                    "passed": True,
                    "failed_check_count": 0,
                    "exit_gate": "METRICS_READY",
                },
                "ANALYTICAL_MART_READY",
                "Metric Engineering",
            )

    def test_statistical_gate_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "STATISTICAL_CORE_READY"):
            require_gate(
                {
                    "passed": True,
                    "failed_check_count": 1,
                    "exit_gate": "STATISTICAL_CORE_READY",
                },
                "STATISTICAL_CORE_READY",
                "Statistical Analysis Core",
            )

    def test_claim_diagnostics_preserve_all_claims(self) -> None:
        frame = self.real_outputs["claim_diagnostics"]

        self.assertEqual(len(frame), 14667)
        self.assertEqual(frame["claim_id"].nunique(), 14667)
        self.assertEqual(frame["generation_id"].nunique(), 638)

    def test_generation_diagnostics_preserve_planned_slots(self) -> None:
        frame = self.real_outputs["generation_diagnostics"]

        self.assertEqual(len(frame), 648)
        self.assertEqual(frame["generation_id"].nunique(), 648)
        self.assertEqual(int(frame["usable"].sum()), 638)

    def test_claim_generation_identity_is_many_to_one(self) -> None:
        claim_frame = build_claim_base_frame(self.real_inputs)
        generations = self.real_inputs["generations"]

        joined = claim_frame[["claim_id", "generation_id"]].merge(
            generations[["generation_id"]],
            on="generation_id",
            how="left",
            validate="many_to_one",
            indicator=True,
        )

        self.assertTrue((joined["_merge"] == "both").all())

    def test_unknown_validation_status_is_rejected(self) -> None:
        broken = self.real_inputs["claims"].head(1).copy()
        broken.loc[broken.index[0], "validation_status"] = "UNKNOWN"

        with self.assertRaisesRegex(ValueError, "unknown"):
            require_known_statuses(broken)

    def test_supported_claim_flags_are_correct(self) -> None:
        frame = self.real_outputs["claim_diagnostics"]
        supported = frame.loc[
            frame["validation_status"] == "SUPPORTED"
        ]

        self.assertTrue(supported["is_applicable"].all())
        self.assertTrue(supported["is_resolved"].all())
        self.assertTrue(supported["is_supported"].all())
        self.assertFalse(supported["is_resolved_error"].any())

    def test_not_verifiable_is_applicable_but_unresolved(self) -> None:
        frame = self.real_outputs["claim_diagnostics"]
        rows = frame.loc[
            frame["validation_status"] == "NOT_VERIFIABLE"
        ]

        self.assertTrue(rows["is_applicable"].all())
        self.assertFalse(rows["is_resolved"].any())
        self.assertFalse(rows["is_resolved_error"].any())

    def test_not_applicable_is_excluded_from_applicable(self) -> None:
        frame = self.real_outputs["claim_diagnostics"]
        rows = frame.loc[
            frame["validation_status"] == "NOT_APPLICABLE"
        ]

        self.assertFalse(rows["is_applicable"].any())
        self.assertTrue(rows["is_not_applicable"].all())

    def test_resolved_error_flags_cover_two_statuses(self) -> None:
        frame = self.real_outputs["claim_diagnostics"]
        expected = frame["validation_status"].isin(
            ["UNSUPPORTED", "CONTRADICTED"]
        )

        self.assertTrue(
            (
                frame["is_resolved_error"].astype(bool)
                == expected
            ).all()
        )

    def test_exact_normalized_match_is_detected(self) -> None:
        result = evaluate_text_pair(
            "  Tín_hiệu tốt! ",
            "tín hiệu tốt",
        )

        self.assertEqual(result["match_type"], "EXACT")
        self.assertTrue(result["exact_match"])
        self.assertTrue(result["contained_match"])
        self.assertEqual(result["token_coverage"], 1.0)

    def test_contained_match_requires_four_phrase_tokens(self) -> None:
        short = evaluate_text_pair(
            "đây là tín hiệu tốt",
            "tín hiệu tốt",
        )
        long = evaluate_text_pair(
            "đây là một tín hiệu rất tốt cho mô hình",
            "tín hiệu rất tốt cho mô hình",
        )

        self.assertFalse(short["contained_match"])
        self.assertTrue(long["contained_match"])

    def test_high_overlap_threshold_is_applied(self) -> None:
        result = evaluate_text_pair(
            "alpha beta gamma delta extra",
            "alpha beta gamma delta epsilon",
        )

        self.assertAlmostEqual(
            result["token_coverage"],
            HIGH_OVERLAP_THRESHOLD,
        )
        self.assertTrue(result["high_overlap_match"])

    def test_claim_candidates_require_matching_identifier(self) -> None:
        claim = SimpleNamespace(
            feature_id="feature_a",
            concept_id=None,
        )
        phrases = [
            {
                "evidence_item_id": "item_a",
                "feature_id": "feature_a",
                "concept_id": None,
            },
            {
                "evidence_item_id": "item_b",
                "feature_id": "feature_b",
                "concept_id": None,
            },
        ]

        candidates = eligible_phrases_for_claim(claim, phrases)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0][0]["evidence_item_id"],
            "item_a",
        )
        self.assertEqual(candidates[0][1], "FEATURE_ID")

    def test_boilerplate_overlap_cannot_cross_feature_ids(self) -> None:
        claim = SimpleNamespace(
            feature_id="feature_a",
            concept_id=None,
        )
        phrases = [
            {
                "evidence_item_id": "other_feature",
                "feature_id": "feature_b",
                "concept_id": None,
                "safe_phrase": (
                    "feature b góp phần làm tăng rủi ro "
                    "dự đoán của mô hình"
                ),
            }
        ]

        self.assertEqual(
            eligible_phrases_for_claim(claim, phrases),
            [],
        )

    def test_phrase_from_another_package_cannot_match(self) -> None:
        one_claim = self.real_outputs["claim_diagnostics"].loc[
            lambda frame: frame["safe_phrase_match_eligible"]
        ].head(1).copy()
        other_package = next(
            package
            for package in self.safe_phrases["package_id"].unique()
            if package != one_claim.iloc[0]["package_id"]
        )
        other_phrases = self.safe_phrases.loc[
            self.safe_phrases["package_id"] == other_package
        ].copy()

        output, matches = match_claims_to_safe_phrases(
            one_claim,
            other_phrases,
        )

        self.assertTrue(matches.empty)
        self.assertFalse(output.iloc[0]["safe_phrase_any_match"])

    def test_exact_match_has_highest_precedence(self) -> None:
        exact = {
            "match_type": "EXACT",
            "token_coverage": 1.0,
            "safe_phrase_item_order": 2,
            "safe_phrase_item_id": "b",
        }
        overlap = {
            "match_type": "HIGH_OVERLAP",
            "token_coverage": 1.0,
            "safe_phrase_item_order": 1,
            "safe_phrase_item_id": "a",
        }

        self.assertLess(
            best_match_sort_key(exact),
            best_match_sort_key(overlap),
        )

    def test_safe_phrase_matching_is_deterministic(self) -> None:
        claims = self.real_outputs["claim_diagnostics"].head(300)
        first_output, first_matches = match_claims_to_safe_phrases(
            claims,
            self.safe_phrases,
        )
        shuffled = self.safe_phrases.sample(
            frac=1.0,
            random_state=42,
        )
        second_output, second_matches = match_claims_to_safe_phrases(
            claims,
            shuffled,
        )

        pd.testing.assert_frame_equal(first_output, second_output)
        pd.testing.assert_frame_equal(first_matches, second_matches)

    def test_usable_loss_decomposition_sums_to_one(self) -> None:
        frame = pd.DataFrame(
            {
                "usable": [True],
                "applicable_count": [10],
                "supported_count": [7],
                "not_verifiable_count": [2],
                "unsupported_count": [1],
                "contradicted_count": [0],
            }
        )

        result = calculate_loss_components(frame).iloc[0]
        total = (
            result["supported_yield_component"]
            + result["pipeline_loss"]
            + result["not_verifiable_loss"]
            + result["unsupported_loss"]
            + result["contradiction_loss"]
        )

        self.assertAlmostEqual(total, 1.0)
        self.assertAlmostEqual(result["total_loss"], 0.3)

    def test_unusable_generation_has_pipeline_loss_one(self) -> None:
        frame = pd.DataFrame(
            {
                "usable": [False],
                "applicable_count": [0],
                "supported_count": [0],
                "not_verifiable_count": [0],
                "unsupported_count": [0],
                "contradicted_count": [0],
            }
        )

        result = calculate_loss_components(frame).iloc[0]

        self.assertEqual(result["pipeline_loss"], 1.0)
        self.assertEqual(result["claim_quality_loss"], 0.0)
        self.assertEqual(result["total_loss"], 1.0)

    def test_supported_component_equals_metric_output(self) -> None:
        frame = self.real_outputs["generation_diagnostics"]

        np.testing.assert_allclose(
            frame["supported_yield_component"],
            frame["end_to_end_faithfulness_yield"],
            rtol=0.0,
            atol=1e-12,
        )

    def test_zero_denominator_returns_nan(self) -> None:
        self.assertTrue(np.isnan(divide_or_nan(1, 0)))

    def test_claim_summary_reconciles_status_totals(self) -> None:
        overall = self.real_outputs["claim_mechanism_summary"].loc[
            lambda frame: frame["group_type"] == "overall"
        ].iloc[0]

        status_total = (
            overall["supported_count"]
            + overall["not_verifiable_count"]
            + overall["unsupported_count"]
            + overall["contradicted_count"]
            + overall["not_applicable_count"]
        )
        self.assertEqual(overall["claim_count"], status_total)
        self.assertEqual(overall["claim_count"], 14667)

    def test_generation_summary_loss_identity_is_exact(self) -> None:
        summary = self.real_outputs["generation_mechanism_summary"]
        total = summary[
            [
                "mean_end_to_end_yield",
                "mean_pipeline_loss",
                "mean_not_verifiable_loss",
                "mean_unsupported_loss",
                "mean_contradiction_loss",
            ]
        ].sum(axis=1)

        np.testing.assert_allclose(
            total,
            np.ones(len(summary)),
            rtol=0.0,
            atol=1e-12,
        )

    def test_pipeline_failures_contain_only_unusable_rows(self) -> None:
        failures = self.real_outputs["pipeline_failures"]
        unusable_ids = set(
            self.real_inputs["generations"].loc[
                ~self.real_inputs["generations"]["usable"].astype(bool),
                "generation_id",
            ]
        )

        self.assertEqual(len(failures), 10)
        self.assertEqual(set(failures["generation_id"]), unusable_ids)

    def test_failure_classification_uses_explicit_precedence(self) -> None:
        row = pd.Series(
            {
                "truncated_response": True,
                "raw_json_parse_success": False,
                "json_parse_success": False,
                "schema_valid": False,
                "runtime_status": "FAILED",
            }
        )

        self.assertEqual(classify_failure(row), "TRUNCATED")

    def test_full_cohort_validation_passes(self) -> None:
        report = validate_diagnostic_outputs(
            self.real_outputs,
            self.real_inputs,
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["failed_check_count"], 0)
        self.assertEqual(report["exit_gate"], OUTPUT_GATE)

    def test_broken_loss_component_fails_validation(self) -> None:
        broken = {
            key: value.copy()
            for key, value in self.real_outputs.items()
        }
        broken["generation_diagnostics"].loc[
            0,
            "not_verifiable_loss",
        ] += 0.1

        report = validate_diagnostic_outputs(broken, self.real_inputs)

        self.assertFalse(report["passed"])
        self.assertGreater(
            report["checks"][
                "generation_loss_decomposition_mismatch_count"
            ]["observed"],
            0,
        )

    def test_duplicate_safe_phrase_pair_fails_validation(self) -> None:
        broken = {
            key: value.copy()
            for key, value in self.real_outputs.items()
        }
        matches = broken["safe_phrase_matches"]
        matches.loc[len(matches)] = matches.iloc[0]

        report = validate_diagnostic_outputs(broken, self.real_inputs)

        self.assertFalse(report["passed"])
        self.assertGreater(
            report["checks"][
                "duplicate_claim_safe_phrase_pair_count"
            ]["observed"],
            0,
        )

    def test_empty_safe_phrase_results_fail_closed(self) -> None:
        broken = {
            key: value.copy()
            for key, value in self.real_outputs.items()
        }
        broken["safe_phrase_matches"] = broken[
            "safe_phrase_matches"
        ].iloc[0:0].copy()

        claims = broken["claim_diagnostics"]
        claims["best_safe_phrase_item_id"] = None
        claims["best_safe_phrase_match_type"] = "NONE"
        claims["best_safe_phrase_token_coverage"] = 0.0
        for column in [
            "safe_phrase_exact_match",
            "safe_phrase_contained_match",
            "safe_phrase_high_overlap",
            "safe_phrase_any_match",
        ]:
            claims[column] = False

        generations = broken["generation_diagnostics"]
        for column in [
            "safe_phrase_matched_claim_count",
            "safe_phrase_exact_claim_count",
            "safe_phrase_contained_claim_count",
            "safe_phrase_high_overlap_claim_count",
        ]:
            generations[column] = 0
        generations["safe_phrase_matched_claim_rate"] = np.where(
            generations["safe_phrase_eligible_claim_count"] > 0,
            0.0,
            np.nan,
        )
        for column in [
            "has_safe_phrase_claim_match",
            "narrative_exact_safe_phrase_match",
            "narrative_contained_safe_phrase_match",
            "narrative_high_overlap_safe_phrase_match",
            "narrative_any_safe_phrase_match",
            "has_any_safe_phrase_match",
        ]:
            generations[column] = False
        generations["narrative_max_safe_phrase_token_coverage"] = 0.0

        broken["claim_mechanism_summary"] = (
            build_claim_mechanism_summary(claims)
        )
        broken["generation_mechanism_summary"] = (
            build_generation_mechanism_summary(generations)
        )

        report = validate_diagnostic_outputs(broken, self.real_inputs)

        self.assertFalse(report["passed"])
        self.assertGreater(
            report["checks"][
                "missing_safe_phrase_match_pair_count"
            ]["observed"],
            0,
        )
        self.assertGreater(
            report["checks"][
                "claim_best_match_reconciliation_mismatch_count"
            ]["observed"],
            0,
        )

    def test_deleted_safe_phrase_pair_fails_validation(self) -> None:
        broken = {
            key: value.copy()
            for key, value in self.real_outputs.items()
        }
        broken["safe_phrase_matches"] = broken[
            "safe_phrase_matches"
        ].iloc[1:].reset_index(drop=True)

        report = validate_diagnostic_outputs(broken, self.real_inputs)

        self.assertFalse(report["passed"])
        self.assertEqual(
            report["checks"][
                "missing_safe_phrase_match_pair_count"
            ]["observed"],
            1,
        )

    def test_swapped_loss_components_fail_validation(self) -> None:
        broken = {
            key: value.copy()
            for key, value in self.real_outputs.items()
        }
        frame = broken["generation_diagnostics"]
        original_nv = frame["not_verifiable_loss"].copy()
        frame["not_verifiable_loss"] = frame["unsupported_loss"]
        frame["unsupported_loss"] = original_nv

        report = validate_diagnostic_outputs(broken, self.real_inputs)

        self.assertFalse(report["passed"])
        self.assertGreater(
            report["checks"][
                "not_verifiable_loss_formula_mismatch_count"
            ]["observed"],
            0,
        )
        self.assertGreater(
            report["checks"][
                "unsupported_loss_formula_mismatch_count"
            ]["observed"],
            0,
        )

    def test_dropped_claim_summary_group_fails_validation(self) -> None:
        broken = {
            key: value.copy()
            for key, value in self.real_outputs.items()
        }
        broken["claim_mechanism_summary"] = broken[
            "claim_mechanism_summary"
        ].iloc[1:].reset_index(drop=True)

        report = validate_diagnostic_outputs(broken, self.real_inputs)

        self.assertFalse(report["passed"])
        self.assertGreater(
            report["checks"][
                "claim_summary_key_set_mismatch_count"
            ]["observed"],
            0,
        )

    def test_altered_safe_phrase_source_text_fails_validation(
        self,
    ) -> None:
        broken = {
            key: value.copy()
            for key, value in self.real_outputs.items()
        }
        broken["safe_phrase_matches"].loc[0, "claim_text"] = (
            "altered source text"
        )

        report = validate_diagnostic_outputs(broken, self.real_inputs)

        self.assertFalse(report["passed"])
        self.assertEqual(
            report["checks"][
                "safe_phrase_match_source_text_mismatch_count"
            ]["observed"],
            1,
        )

    def test_validation_check_name_set_is_fixed(self) -> None:
        report = validate_diagnostic_outputs(
            self.real_outputs,
            self.real_inputs,
        )

        self.assertEqual(report["check_count"], 63)
        self.assertTrue(
            report["checks"]["missing_validation_check_names"][
                "passed"
            ]
        )
        self.assertTrue(
            report["checks"]["extra_validation_check_names"][
                "passed"
            ]
        )

    def test_missing_validation_branch_fails_closed(self) -> None:
        with patch.object(
            validate_module,
            "validate_safe_phrase_matches",
            return_value=None,
        ):
            report = validate_diagnostic_outputs(
                self.real_outputs,
                self.real_inputs,
            )

        self.assertFalse(report["passed"])
        missing = report["checks"][
            "missing_validation_check_names"
        ]["observed"]
        self.assertIn("expected_safe_phrase_match_pair_count", missing)

    def test_best_match_summary_is_exclusive(self) -> None:
        summary = self.real_outputs["claim_mechanism_summary"]
        exclusive_total = summary[
            [
                "safe_phrase_best_exact_claim_count",
                "safe_phrase_best_contained_claim_count",
                "safe_phrase_best_high_overlap_claim_count",
                "safe_phrase_best_none_claim_count",
            ]
        ].sum(axis=1)

        pd.testing.assert_series_equal(
            exclusive_total.astype(int),
            summary["safe_phrase_eligible_claim_count"].astype(int),
            check_names=False,
        )

    def test_project_root_is_found_from_another_working_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(DEFAULT_PATHS.project_root)
            command = [
                sys.executable,
                "-c",
                (
                    "from research.python.common.paths import "
                    "DEFAULT_PATHS; print(DEFAULT_PATHS.project_root)"
                ),
            ]
            result = subprocess.run(
                command,
                cwd=temporary_directory,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertEqual(
            Path(result.stdout.strip()),
            DEFAULT_PATHS.project_root,
        )
        self.assertEqual(
            find_project_root(Path(__file__)),
            DEFAULT_PATHS.project_root,
        )

    def test_integration_writes_six_csvs_and_validation_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            csv_paths = {
                "CLAIM_DIAGNOSTICS_PATH": output_dir
                / "claim_diagnostics.csv",
                "GENERATION_DIAGNOSTICS_PATH": output_dir
                / "generation_diagnostics.csv",
                "CLAIM_MECHANISM_SUMMARY_PATH": output_dir
                / "claim_mechanism_summary.csv",
                "GENERATION_MECHANISM_SUMMARY_PATH": output_dir
                / "generation_mechanism_summary.csv",
                "SAFE_PHRASE_MATCHES_PATH": output_dir
                / "safe_phrase_matches.csv",
                "PIPELINE_FAILURES_PATH": output_dir
                / "pipeline_failures.csv",
            }
            validation_path = output_dir / "diagnostic_validation.json"

            patches = [
                patch.object(build_module, "OUTPUT_DIR", output_dir),
                *[
                    patch.object(build_module, name, path)
                    for name, path in csv_paths.items()
                ],
                patch.object(
                    validate_module,
                    "DIAGNOSTIC_VALIDATION_PATH",
                    validation_path,
                ),
            ]

            for active_patch in patches:
                active_patch.start()
            try:
                write_diagnostic_outputs(self.real_outputs)
                report = validate_diagnostic_outputs(
                    self.real_outputs,
                    self.real_inputs,
                )
                write_validation_report(report)
            finally:
                for active_patch in reversed(patches):
                    active_patch.stop()

            for path in csv_paths.values():
                self.assertTrue(path.is_file())
            self.assertTrue(validation_path.is_file())


if __name__ == "__main__":
    unittest.main()
