"""Unit, integration và mutation tests cho Decision Support Core."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from research.python.decision_support import build as build_module
from research.python.decision_support import validate as validate_module
from research.python.decision_support.build import (
    build_decision_outputs,
    build_recommendations,
    build_scenario_rankings,
)
from research.python.decision_support.config import (
    DECISION_VERSION,
    EXPECTED_COUNTS,
    SCENARIOS,
)
from research.python.decision_support.evidence import (
    build_recommendation_evidence,
    classify_evidence,
)
from research.python.decision_support.load import (
    load_decision_inputs,
    require_upstream_gates,
)
from research.python.decision_support.pareto import option_dominates
from research.python.decision_support.scoring import (
    build_scenario_definitions,
    constraint_passes,
    normalize_value,
)
from research.python.decision_support.validate import (
    validate_decision_outputs,
)


class DecisionSupportTests(unittest.TestCase):
    """Dùng upstream outputs thật để khóa behavior của batch."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.input_data = load_decision_inputs()
        cls.outputs = build_decision_outputs(cls.input_data)
        cls.report = validate_decision_outputs(cls.outputs, cls.input_data)

    def cloned_outputs(self) -> dict[str, pd.DataFrame]:
        return {
            name: dataframe.copy(deep=True)
            for name, dataframe in self.outputs.items()
        }

    # ---------- Input gates ----------

    def test_01_metric_gate_failure_blocks(self) -> None:
        metric = copy.deepcopy(self.input_data["metric_validation"])
        metric["passed"] = False
        with self.assertRaises(ValueError):
            require_upstream_gates(
                metric,
                self.input_data["statistical_validation"],
                self.input_data["diagnostic_validation"],
            )

    def test_02_statistical_gate_failure_blocks(self) -> None:
        statistical = copy.deepcopy(
            self.input_data["statistical_validation"]
        )
        statistical["failed_check_count"] = 1
        with self.assertRaises(ValueError):
            require_upstream_gates(
                self.input_data["metric_validation"],
                statistical,
                self.input_data["diagnostic_validation"],
            )

    def test_03_diagnostic_gate_failure_blocks(self) -> None:
        diagnostic = copy.deepcopy(self.input_data["diagnostic_validation"])
        diagnostic["exit_gate"] = "DIAGNOSTICS_INVALID"
        with self.assertRaises(ValueError):
            require_upstream_gates(
                self.input_data["metric_validation"],
                self.input_data["statistical_validation"],
                diagnostic,
            )

    def test_04_diagnostics_v1_0_is_rejected(self) -> None:
        diagnostic = copy.deepcopy(self.input_data["diagnostic_validation"])
        diagnostic["diagnostic_version"] = "v1.0"
        with self.assertRaises(ValueError):
            require_upstream_gates(
                self.input_data["metric_validation"],
                self.input_data["statistical_validation"],
                diagnostic,
            )

    # ---------- Option table ----------

    def test_05_exactly_18_options(self) -> None:
        self.assertEqual(len(self.outputs["decision_options"]), 18)

    def test_06_each_option_has_36_generations(self) -> None:
        observed = self.outputs["decision_options"][
            "planned_generation_count"
        ]
        self.assertTrue((observed == 36).all())

    def test_07_option_ids_are_unique(self) -> None:
        self.assertFalse(
            self.outputs["decision_options"]["option_id"].duplicated().any()
        )

    def test_08_mean_e2e_is_recalculated(self) -> None:
        raw = self.input_data["generation_diagnostics"]
        expected = raw.groupby(
            ["model_id", "evidence_level"]
        )["end_to_end_faithfulness_yield"].mean()
        options = self.outputs["decision_options"].set_index(
            ["model_id", "evidence_level"]
        )
        self.assertTrue(
            np.allclose(
                options.loc[expected.index, "mean_end_to_end_yield"],
                expected,
                rtol=0.0,
                atol=1e-12,
            )
        )

    def test_09_p10_is_recalculated(self) -> None:
        raw = self.input_data["generation_diagnostics"]
        expected = raw.groupby(
            ["model_id", "evidence_level"]
        )["end_to_end_faithfulness_yield"].quantile(0.10)
        options = self.outputs["decision_options"].set_index(
            ["model_id", "evidence_level"]
        )
        self.assertTrue(
            np.allclose(
                options.loc[expected.index, "p10_end_to_end_yield"],
                expected,
                rtol=0.0,
                atol=1e-12,
            )
        )

    def test_10_unusable_generations_remain_in_primary_population(self) -> None:
        raw = self.input_data["generation_diagnostics"]
        unusable = raw.loc[~raw["usable"].astype(bool)]
        self.assertEqual(len(unusable), 10)
        self.assertTrue(
            (unusable["end_to_end_faithfulness_yield"] == 0.0).all()
        )

    def test_11_option_loss_components_sum_to_one(self) -> None:
        options = self.outputs["decision_options"]
        total = (
            options["mean_end_to_end_yield"]
            + options["mean_pipeline_loss"]
            + options["mean_not_verifiable_loss"]
            + options["mean_unsupported_loss"]
            + options["mean_contradiction_loss"]
        )
        self.assertTrue(np.allclose(total, 1.0, atol=1e-12, rtol=0.0))

    def test_12_best_match_categories_are_exclusive(self) -> None:
        options = self.outputs["decision_options"]
        total = (
            options["safe_phrase_best_exact_claim_count"]
            + options["safe_phrase_best_contained_claim_count"]
            + options["safe_phrase_best_high_overlap_claim_count"]
            + options["safe_phrase_best_none_claim_count"]
        )
        self.assertTrue(
            (
                total
                == options["safe_phrase_eligible_claim_count"]
            ).all()
        )

    def test_13_strong_signal_uses_exact_plus_contained(self) -> None:
        options = self.outputs["decision_options"]
        expected = (
            options["safe_phrase_best_exact_claim_count"]
            + options["safe_phrase_best_contained_claim_count"]
        )
        self.assertTrue(
            (expected == options["strong_safe_phrase_signal_count"]).all()
        )

    def test_14_s0_and_s1_have_zero_overlap_signal(self) -> None:
        options = self.outputs["decision_options"]
        no_phrase = options["evidence_level"].isin(["S0", "S1"])
        self.assertTrue(
            (
                options.loc[
                    no_phrase,
                    "strong_safe_phrase_signal_share_all_claims",
                ]
                == 0.0
            ).all()
        )

    # ---------- Scenario definitions and normalization ----------

    def test_15_exactly_five_scenarios(self) -> None:
        definitions = self.outputs["scenario_definitions"]
        self.assertEqual(definitions["scenario_id"].nunique(), 5)

    def test_16_scenario_weights_sum_to_one(self) -> None:
        definitions = self.outputs["scenario_definitions"]
        objectives = definitions.loc[
            definitions["rule_type"] == "WEIGHTED_OBJECTIVE"
        ]
        sums = objectives.groupby("scenario_id")["weight"].sum()
        self.assertTrue(np.allclose(sums, 1.0, atol=1e-12, rtol=0.0))

    def test_17_constraint_minimum_is_enforced(self) -> None:
        self.assertTrue(constraint_passes(0.95, 0.95, None))
        self.assertFalse(constraint_passes(0.949, 0.95, None))

    def test_18_constraint_maximum_is_enforced(self) -> None:
        self.assertTrue(constraint_passes(0.0, None, 0.0))
        self.assertFalse(constraint_passes(0.01, None, 0.0))

    def test_19_null_constraint_value_fails_closed(self) -> None:
        self.assertFalse(constraint_passes(np.nan, 0.5, None))

    def test_20_constant_metric_normalizes_to_one(self) -> None:
        self.assertEqual(normalize_value(3.0, 3.0, 3.0, "MAX"), 1.0)

    def test_21_benefit_normalization_direction(self) -> None:
        self.assertEqual(normalize_value(10.0, 0.0, 10.0, "MAX"), 1.0)
        self.assertEqual(normalize_value(0.0, 0.0, 10.0, "MAX"), 0.0)

    def test_22_cost_normalization_direction(self) -> None:
        self.assertEqual(normalize_value(0.0, 0.0, 10.0, "MIN"), 1.0)
        self.assertEqual(normalize_value(10.0, 0.0, 10.0, "MIN"), 0.0)

    def test_23_ineligible_option_has_null_utility(self) -> None:
        rankings = self.outputs["scenario_rankings"]
        ineligible = rankings.loc[~rankings["eligible"].astype(bool)]
        self.assertFalse(ineligible.empty)
        self.assertTrue(ineligible["utility_score"].isna().all())

    def test_24_normalized_scores_are_bounded(self) -> None:
        values = self.outputs["scenario_criterion_scores"][
            "normalized_value"
        ].dropna()
        self.assertTrue(((values >= 0.0) & (values <= 1.0)).all())

    # ---------- Pareto and ranking ----------

    def test_25_pareto_dominance_for_benefit_metrics(self) -> None:
        rules = pd.DataFrame(
            [
                {"criterion_id": "quality", "direction": "MAX"},
                {"criterion_id": "reliability", "direction": "MAX"},
            ]
        )
        a = pd.Series({"quality": 0.9, "reliability": 1.0})
        b = pd.Series({"quality": 0.8, "reliability": 1.0})
        self.assertTrue(option_dominates(a, b, rules))
        self.assertFalse(option_dominates(b, a, rules))

    def test_26_tied_options_do_not_dominate(self) -> None:
        rules = pd.DataFrame(
            [{"criterion_id": "quality", "direction": "MAX"}]
        )
        a = pd.Series({"quality": 0.9})
        b = pd.Series({"quality": 0.9})
        self.assertFalse(option_dominates(a, b, rules))

    def test_27_all_recommendations_are_pareto_optimal(self) -> None:
        self.assertTrue(
            self.outputs["recommendations"][
                "is_pareto_optimal"
            ].astype(bool).all()
        )

    def test_28_one_primary_recommendation_per_scenario(self) -> None:
        primary = self.outputs["recommendations"].loc[
            self.outputs["recommendations"]["recommendation_role"]
            == "PRIMARY"
        ]
        counts = primary.groupby("scenario_id").size()
        self.assertTrue((counts == 1).all())

    def test_29_at_most_three_recommendations_per_scenario(self) -> None:
        counts = self.outputs["recommendations"].groupby(
            "scenario_id"
        ).size()
        self.assertTrue((counts <= 3).all())

    def test_30_ranking_is_deterministic(self) -> None:
        definitions = build_scenario_definitions()
        from research.python.decision_support.scoring import build_scenario_scores
        from research.python.decision_support.pareto import build_pareto_frontier

        _, base = build_scenario_scores(
            self.outputs["decision_options"],
            definitions,
        )
        pareto = build_pareto_frontier(base, definitions)
        rebuilt = build_scenario_rankings(base, pareto)
        self.assertEqual(
            rebuilt[["scenario_id", "option_id"]].to_dict("records"),
            self.outputs["scenario_rankings"][
                ["scenario_id", "option_id"]
            ].to_dict("records"),
        )

    # ---------- Statistical evidence ----------

    def test_31_significant_advantage_classification(self) -> None:
        self.assertEqual(
            classify_evidence(0.01, 0.2),
            "SIGNIFICANT_ADVANTAGE",
        )

    def test_32_significant_disadvantage_classification(self) -> None:
        self.assertEqual(
            classify_evidence(0.01, -0.2),
            "SIGNIFICANT_DISADVANTAGE",
        )

    def test_33_non_significant_classification(self) -> None:
        self.assertEqual(
            classify_evidence(0.2, 0.2),
            "NO_SIGNIFICANT_DIFFERENCE",
        )

    def test_34_evidence_has_85_rows(self) -> None:
        self.assertEqual(
            len(self.outputs["recommendation_evidence"]),
            EXPECTED_COUNTS["recommendation_evidence_rows"],
        )

    def test_35_each_primary_has_17_comparators(self) -> None:
        counts = self.outputs["recommendation_evidence"].groupby(
            "scenario_id"
        ).size()
        self.assertTrue((counts == 17).all())

    def test_36_untested_pair_stays_not_tested(self) -> None:
        evidence = self.outputs["recommendation_evidence"]
        untested = evidence.loc[~evidence["comparison_available"].astype(bool)]
        self.assertFalse(untested.empty)
        self.assertTrue((untested["evidence_status"] == "NOT_TESTED").all())

    def test_37_b_orientation_negates_mean_difference(self) -> None:
        evidence = self.outputs["recommendation_evidence"]
        b_rows = evidence.loc[
            evidence["comparison_orientation"] == "RECOMMENDATION_IS_B"
        ]
        self.assertFalse(b_rows.empty)
        row = b_rows.iloc[0]
        pair = self.input_data["paired_tests"]
        matching = pair.loc[
            (
                pair["condition_b_model_id"].astype(str)
                + "__"
                + pair["condition_b_evidence_level"].astype(str)
                == row["recommended_option_id"]
            )
            & (
                pair["condition_a_model_id"].astype(str)
                + "__"
                + pair["condition_a_evidence_level"].astype(str)
                == row["comparator_option_id"]
            )
        ].iloc[0]
        self.assertAlmostEqual(
            row["oriented_mean_difference"],
            -matching["mean_difference"],
            places=12,
        )

    # ---------- Validation and mutation tests ----------

    def test_38_valid_outputs_pass_gate(self) -> None:
        self.assertTrue(self.report["passed"])
        self.assertEqual(self.report["failed_check_count"], 0)
        self.assertEqual(self.report["exit_gate"], "DECISION_SUPPORT_READY")

    def test_39_delete_option_fails_validation(self) -> None:
        outputs = self.cloned_outputs()
        outputs["decision_options"] = outputs["decision_options"].iloc[1:]
        report = validate_decision_outputs(outputs, self.input_data)
        self.assertFalse(report["passed"])

    def test_40_alter_mean_quality_fails_validation(self) -> None:
        outputs = self.cloned_outputs()
        outputs["decision_options"].loc[0, "mean_end_to_end_yield"] += 0.1
        report = validate_decision_outputs(outputs, self.input_data)
        self.assertFalse(report["passed"])

    def test_41_swap_latency_fails_validation(self) -> None:
        outputs = self.cloned_outputs()
        column = "mean_latency_seconds_planned"
        outputs["decision_options"].loc[[0, 1], column] = (
            outputs["decision_options"].loc[[1, 0], column].to_numpy()
        )
        report = validate_decision_outputs(outputs, self.input_data)
        self.assertFalse(report["passed"])

    def test_42_invalid_scenario_weight_fails_validation(self) -> None:
        outputs = self.cloned_outputs()
        mask = outputs["scenario_definitions"]["rule_type"] == "WEIGHTED_OBJECTIVE"
        first_index = outputs["scenario_definitions"].index[mask][0]
        outputs["scenario_definitions"].loc[first_index, "weight"] += 0.1
        report = validate_decision_outputs(outputs, self.input_data)
        self.assertFalse(report["passed"])

    def test_43_altered_normalized_value_fails_validation(self) -> None:
        outputs = self.cloned_outputs()
        index = outputs["scenario_criterion_scores"][
            "normalized_value"
        ].first_valid_index()
        outputs["scenario_criterion_scores"].loc[
            index,
            "normalized_value",
        ] = 0.123456
        report = validate_decision_outputs(outputs, self.input_data)
        self.assertFalse(report["passed"])

    def test_44_ineligible_utility_fails_validation(self) -> None:
        outputs = self.cloned_outputs()
        mask = ~outputs["scenario_rankings"]["eligible"].astype(bool)
        index = outputs["scenario_rankings"].index[mask][0]
        outputs["scenario_rankings"].loc[index, "utility_score"] = 0.5
        report = validate_decision_outputs(outputs, self.input_data)
        self.assertFalse(report["passed"])

    def test_45_wrong_pareto_flag_fails_validation(self) -> None:
        outputs = self.cloned_outputs()
        index = outputs["pareto_frontier"].index[0]
        current = bool(
            outputs["pareto_frontier"].loc[index, "is_pareto_optimal"]
        )
        outputs["pareto_frontier"].loc[
            index,
            "is_pareto_optimal",
        ] = not current
        report = validate_decision_outputs(outputs, self.input_data)
        self.assertFalse(report["passed"])

    def test_46_wrong_recommendation_fails_validation(self) -> None:
        outputs = self.cloned_outputs()
        outputs["recommendations"].loc[0, "option_id"] = "fake__S0"
        report = validate_decision_outputs(outputs, self.input_data)
        self.assertFalse(report["passed"])

    def test_47_wrong_evidence_orientation_fails_validation(self) -> None:
        outputs = self.cloned_outputs()
        available = outputs["recommendation_evidence"][
            "comparison_available"
        ].astype(bool)
        index = outputs["recommendation_evidence"].index[available][0]
        outputs["recommendation_evidence"].loc[
            index,
            "oriented_rank_biserial_correlation",
        ] *= -1
        report = validate_decision_outputs(outputs, self.input_data)
        self.assertFalse(report["passed"])

    def test_48_not_tested_status_mutation_fails_validation(self) -> None:
        outputs = self.cloned_outputs()
        mask = outputs["recommendation_evidence"]["evidence_status"] == "NOT_TESTED"
        index = outputs["recommendation_evidence"].index[mask][0]
        outputs["recommendation_evidence"].loc[
            index,
            "evidence_status",
        ] = "NO_SIGNIFICANT_DIFFERENCE"
        report = validate_decision_outputs(outputs, self.input_data)
        self.assertFalse(report["passed"])

    def test_49_missing_validation_branch_fails_closed(self) -> None:
        with patch.object(
            validate_module,
            "validate_scenario_outputs",
            lambda checks, outputs, input_data: None,
        ):
            report = validate_module.validate_decision_outputs(
                self.outputs,
                self.input_data,
            )
        self.assertFalse(report["passed"])
        missing = report["checks"]["missing_validation_check_names"]
        self.assertFalse(missing["passed"])

    def test_50_running_from_another_cwd_finds_project_root(self) -> None:
        project_root = Path(__file__).resolve().parents[4]
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(project_root)
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from research.python.decision_support.config "
                        "import PROJECT_ROOT; print(PROJECT_ROOT)"
                    ),
                ],
                cwd=temporary_directory,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertEqual(Path(result.stdout.strip()), project_root)

    def test_51_integration_writes_eight_outputs(self) -> None:
        outputs = self.cloned_outputs()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path_names = {
                "DECISION_OPTIONS_PATH": root / "decision_options.csv",
                "SCENARIO_DEFINITIONS_PATH": root / "scenario_definitions.csv",
                "SCENARIO_CRITERION_SCORES_PATH": (
                    root / "scenario_criterion_scores.csv"
                ),
                "SCENARIO_RANKINGS_PATH": root / "scenario_rankings.csv",
                "PARETO_FRONTIER_PATH": root / "pareto_frontier.csv",
                "RECOMMENDATIONS_PATH": root / "recommendations.csv",
                "RECOMMENDATION_EVIDENCE_PATH": root / "recommendation_evidence.csv",
            }
            with patch.multiple(build_module, **path_names):
                build_module.write_decision_outputs(outputs)
            with patch.object(
                validate_module,
                "DECISION_VALIDATION_PATH",
                root / "decision_validation.json",
            ):
                validate_module.write_validation_report(self.report)

            self.assertEqual(len(list(root.iterdir())), 8)

    def test_52_two_builds_are_identical(self) -> None:
        second = build_decision_outputs(self.input_data)
        for name in self.outputs:
            pd.testing.assert_frame_equal(
                self.outputs[name],
                second[name],
                check_dtype=True,
                check_exact=True,
            )


    # ---------- Decision Support v1.1 metadata ----------

    def test_53_decision_version_is_v1_1(self) -> None:
        self.assertEqual(DECISION_VERSION, "v1.1")
        self.assertTrue(
            (self.outputs["decision_options"]["decision_version"] == "v1.1").all()
        )

    def test_54_utility_rank_uses_direct_utility_order(self) -> None:
        rankings = self.outputs["scenario_rankings"]
        for _, group in rankings.groupby("scenario_id", sort=False):
            scored = group.loc[
                group["eligible"].astype(bool)
                & group["score_available"].astype(bool)
            ].sort_values(
                [
                    "utility_score",
                    "mean_end_to_end_yield",
                    "usability_rate",
                    "mean_latency_seconds_planned",
                    "model_order",
                    "evidence_order",
                ],
                ascending=[False, False, False, True, True, True],
                kind="stable",
            )
            self.assertEqual(
                scored["utility_rank"].astype(int).tolist(),
                list(range(1, len(scored) + 1)),
            )

    def test_55_alternatives_use_pareto_reason_code(self) -> None:
        recommendations = self.outputs["recommendations"]
        alternatives = recommendations.loc[
            recommendations["recommendation_role"] == "ALTERNATIVE"
        ]
        self.assertFalse(alternatives.empty)
        for value in alternatives["reason_codes"]:
            codes = json.loads(value)
            self.assertIn("TOP_PARETO_ALTERNATIVE", codes)
            self.assertNotIn("TOP_THREE_SCENARIO_UTILITY", codes)
            self.assertNotIn("TOP_SCENARIO_UTILITY", codes)

    def test_56_deprecated_reason_code_fails_validation(self) -> None:
        outputs = self.cloned_outputs()
        alternatives = outputs["recommendations"][
            "recommendation_role"
        ] == "ALTERNATIVE"
        index = outputs["recommendations"].index[alternatives][0]
        codes = json.loads(outputs["recommendations"].at[index, "reason_codes"])
        codes.remove("TOP_PARETO_ALTERNATIVE")
        codes.append("TOP_THREE_SCENARIO_UTILITY")
        outputs["recommendations"].at[index, "reason_codes"] = json.dumps(
            codes,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        report = validate_decision_outputs(outputs, self.input_data)
        self.assertFalse(report["passed"])
        self.assertFalse(
            report["checks"][
                "recommendation_reason_code_mismatch_count"
            ]["passed"]
        )


if __name__ == "__main__":
    unittest.main()
