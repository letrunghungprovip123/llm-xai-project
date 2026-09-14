"""Integration tests for research-complete visualization marts v2."""

from __future__ import annotations

import unittest

from research.python.visualization_v2.build import build_outputs
from research.python.visualization_v2.load import load_visualization_v2_inputs
from research.python.visualization_v2.validate import validate_outputs


class VisualizationV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = load_visualization_v2_inputs()
        cls.outputs = build_outputs(cls.inputs)
        cls.validation = validate_outputs(cls.outputs, cls.inputs)

    def test_01_six_research_questions_are_locked(self) -> None:
        registry = self.outputs["research_question_registry"]
        self.assertEqual(registry["rq_id"].tolist(), [
            "RQ1", "RQ2", "RQ3", "RQ4", "RQ5", "RQ6"
        ])

    def test_02_rq6_requires_baseline_ready(self) -> None:
        registry = self.outputs["research_question_registry"].set_index("rq_id")
        self.assertEqual(
            registry.loc["RQ6", "status"],
            "ACTIVE_AFTER_BASELINE_COMPARISON_READY",
        )
        self.assertEqual(
            self.inputs["baseline_validation"]["exit_gate"],
            "BASELINE_COMPARISON_READY",
        )

    def test_03_evidence_design_has_216_case_conditions(self) -> None:
        frame = self.outputs["evidence_design_summary"]
        self.assertEqual(len(frame), 216)
        self.assertFalse(frame.duplicated(["case_id", "evidence_level"]).any())
        self.assertTrue((~frame["evidence_condition_is_ordinal"]).all())

    def test_04_utilization_uses_648_llm_and_216_template_rows(self) -> None:
        frame = self.outputs["evidence_utilization_summary"]
        self.assertEqual(
            frame["generator_family"].value_counts().to_dict(),
            {"LLM": 648, "TEMPLATE": 216},
        )

    def test_05_narrative_structure_has_policy_fields(self) -> None:
        frame = self.outputs["narrative_structure_summary"]
        self.assertEqual(len(frame), 864)
        self.assertIn("overall_policy_compliant", frame.columns)
        self.assertTrue((~frame["human_naturalness_measured"]).all())

    def test_06_case_heterogeneity_has_threshold_bands(self) -> None:
        frame = self.outputs["case_heterogeneity_summary"]
        self.assertEqual(len(frame), 864)
        self.assertIn("threshold_distance_band", frame.columns)
        self.assertEqual(frame["case_id"].nunique(), 36)

    def test_07_primary_option_table_excludes_template(self) -> None:
        options = self.outputs["option_performance"]
        self.assertEqual(len(options), 18)
        self.assertFalse(options["model_id"].eq("template_baseline").any())

    def test_08_decision_scenarios_exclude_template(self) -> None:
        scenarios = self.outputs["scenario_options"]
        self.assertFalse(
            scenarios["option_id"].astype(str).str.contains(
                "template", case=False
            ).any()
        )

    def test_09_baseline_pair_table_is_available(self) -> None:
        self.assertEqual(len(self.outputs["llm_vs_template_case_pairs"]), 648)
        self.assertEqual(len(self.outputs["llm_vs_template_tests"]), 105)

    def test_10_s0_is_control_not_baseline(self) -> None:
        for frame in self.outputs.values():
            object_frame = frame.select_dtypes(include=["object", "string"])
            self.assertFalse(
                object_frame.fillna("").astype(str).apply(
                    lambda column: column.str.contains(
                        "Prediction-only baseline", regex=False
                    ).any()
                ).any()
            )

    def test_11_metric_visibility_has_four_tiers(self) -> None:
        frame = self.outputs["metric_visibility_registry"]
        self.assertEqual(frame["visibility_tier"].nunique(), 4)
        disabled = frame.loc[
            frame["visibility_tier"] == "D_DISABLED_UNTIL_BETTER_DATA"
        ]
        self.assertTrue((~disabled["dashboard_enabled"]).all())

    def test_12_dictionary_covers_every_output_field(self) -> None:
        expected = sum(
            len(frame.columns)
            for name, frame in self.outputs.items()
            if name != "visualization_dictionary"
        )
        self.assertEqual(len(self.outputs["visualization_dictionary"]), expected)

    def test_13_release_metadata_keeps_template_separate(self) -> None:
        row = self.outputs["release_metadata"].iloc[0]
        self.assertFalse(bool(row["template_is_fourth_llm"]))
        self.assertFalse(bool(row["template_eligible_for_decision_ranking"]))
        self.assertFalse(bool(row["human_naturalness_evaluated"]))

    def test_14_certified_statistical_tables_are_present(self) -> None:
        self.assertEqual(len(self.outputs["omnibus_tests"]), 3)
        self.assertEqual(len(self.outputs["paired_tests"]), 33)
        self.assertEqual(len(self.outputs["conditional_paired_tests"]), 99)
        self.assertEqual(
            len(self.outputs["complete_case_omnibus_tests"]), 3
        )

    def test_15_validator_sensitivity_tables_are_present(self) -> None:
        self.assertEqual(len(self.outputs["validator_generation_pairs"]), 648)
        self.assertEqual(len(self.outputs["validator_metric_summary"]), 112)
        self.assertEqual(len(self.outputs["validator_sensitivity_tests"]), 40)

    def test_16_report_and_baseline_artifacts_are_hash_verified(self) -> None:
        self.assertEqual(
            len(self.inputs["verified_report_paths"]),
            len(self.inputs["report_manifest"]["certified_report_files"]),
        )
        self.assertEqual(
            len(self.inputs["verified_baseline_paths"]),
            len(self.inputs["baseline_manifest"]["output_artifacts"]),
        )

    def test_17_release_metadata_carries_parent_commit(self) -> None:
        row = self.outputs["release_metadata"].iloc[0]
        self.assertTrue(str(row["parent_git_commit"]).strip())
        self.assertNotEqual(str(row["parent_git_commit"]).lower(), "nan")

    def test_18_visualization_v2_gate_is_ready(self) -> None:
        self.assertTrue(self.validation["passed"])
        self.assertEqual(
            self.validation["exit_gate"], "VISUALIZATION_DATA_V2_READY"
        )


if __name__ == "__main__":
    unittest.main()
