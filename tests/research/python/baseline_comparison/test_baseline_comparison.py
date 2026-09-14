"""Integration tests for deterministic Template Baseline analysis."""

from __future__ import annotations

import unittest

import numpy as np

from research.python.baseline_comparison.build import build_outputs
from research.python.baseline_comparison.load import load_baseline_inputs
from research.python.baseline_comparison.validate import validate_outputs


class BaselineComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = load_baseline_inputs()
        cls.outputs = build_outputs(cls.inputs)
        cls.validation = validate_outputs(cls.outputs, cls.inputs)

    def test_01_baseline_has_216_generations(self) -> None:
        self.assertEqual(len(self.outputs["baseline_generation_metrics"]), 216)

    def test_02_baseline_matrix_is_36_by_6(self) -> None:
        metrics = self.outputs["baseline_generation_metrics"]
        self.assertEqual(metrics["case_id"].nunique(), 36)
        self.assertEqual(metrics["evidence_level"].nunique(), 6)
        self.assertFalse(metrics.duplicated(["case_id", "evidence_level"]).any())

    def test_03_all_template_generations_are_usable(self) -> None:
        self.assertTrue(
            self.outputs["baseline_generation_metrics"]["usable"].astype(bool).all()
        )

    def test_04_claim_ids_are_deterministic_and_unique(self) -> None:
        claims = self.outputs["baseline_claims"]
        self.assertFalse(claims["claim_id"].duplicated().any())
        rebuilt = build_outputs(self.inputs)["baseline_claims"]
        self.assertTrue(claims["claim_id"].equals(rebuilt["claim_id"]))

    def test_05_applicable_claim_statuses_partition(self) -> None:
        claims = self.outputs["baseline_claims"]
        applicable = claims.loc[claims["is_applicable"].astype(bool)]
        partition = applicable[
            [
                "is_supported",
                "is_not_verifiable",
                "is_unsupported",
                "is_contradicted",
            ]
        ].astype(int).sum(axis=1)
        self.assertEqual(set(partition), {1})

    def test_06_usable_e2e_equals_conservative(self) -> None:
        metrics = self.outputs["baseline_generation_metrics"]
        self.assertTrue(
            np.allclose(
                metrics["end_to_end_faithfulness_yield"],
                metrics["conservative_faithfulness"],
                atol=1e-12,
                rtol=0.0,
                equal_nan=True,
            )
        )

    def test_07_baseline_has_six_option_rows(self) -> None:
        options = self.outputs["baseline_option_performance"]
        self.assertEqual(len(options), 6)
        self.assertTrue((~options["eligible_for_llm_decision_ranking"]).all())

    def test_08_llm_template_pair_count_is_648(self) -> None:
        pairs = self.outputs["llm_vs_template_case_pairs"]
        self.assertEqual(len(pairs), 648)
        self.assertFalse(
            pairs.duplicated(["case_id", "model_id", "evidence_level"]).any()
        )

    def test_09_summary_has_24_rows(self) -> None:
        summary = self.outputs["llm_vs_template_summary"]
        self.assertEqual(len(summary), 24)
        self.assertEqual(
            summary["group_type"].value_counts().to_dict(),
            {
                "model_evidence": 18,
                "model_overall": 3,
                "model_s1_s4_case_aggregate": 3,
            },
        )

    def test_10_tests_have_105_rows(self) -> None:
        tests = self.outputs["llm_vs_template_tests"]
        self.assertEqual(len(tests), 105)
        self.assertTrue(tests["planned_pair_count"].eq(36).all())
        self.assertTrue(
            (
                tests["paired_case_count"] + tests["excluded_pair_count"]
                == 36
            ).all()
        )

    def test_11_primary_e2e_uses_all_cases(self) -> None:
        tests = self.outputs["llm_vs_template_tests"]
        e2e = tests.loc[
            tests["metric_id"] == "end_to_end_faithfulness_yield"
        ]
        self.assertEqual(set(e2e["paired_case_count"]), {36})

    def test_12_conditional_s4_exposes_missing_pairs(self) -> None:
        tests = self.outputs["llm_vs_template_tests"]
        conditional_s4 = tests.loc[
            (tests["metric_id"] == "conservative_faithfulness")
            & (tests["evidence_level"] == "S4")
        ]
        self.assertTrue((conditional_s4["excluded_pair_count"] > 0).any())

    def test_13_holm_values_are_bounded(self) -> None:
        tests = self.outputs["llm_vs_template_tests"]
        self.assertTrue(tests["adjusted_p_value"].between(0.0, 1.0).all())

    def test_14_parent_report_artifacts_are_hash_verified(self) -> None:
        self.assertEqual(
            len(self.inputs["verified_report_paths"]),
            len(self.inputs["report_manifest"]["certified_report_files"]),
        )

    def test_15_validation_gate_is_ready(self) -> None:
        self.assertTrue(self.validation["passed"])
        self.assertEqual(
            self.validation["exit_gate"], "BASELINE_COMPARISON_READY"
        )
        self.assertFalse(
            self.validation["claim_extraction_channel_identical_to_llm"]
        )
        self.assertFalse(self.validation["human_naturalness_evaluated"])


if __name__ == "__main__":
    unittest.main()
