"""Tests for balanced repeated-measures statistical analysis."""

from __future__ import annotations

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

from research.python.common.paths import DEFAULT_PATHS, find_project_root
from research.python.statistical_analysis import build as build_module
from research.python.statistical_analysis.build import (
    build_statistical_outputs,
    write_statistical_outputs,
)
from research.python.statistical_analysis.config import (
    EXPECTED_COUNTS,
    OUTPUT_EXIT_GATE,
    PRIMARY_METRIC,
)
from research.python.statistical_analysis.inference import (
    build_balanced_array,
    build_paired_tests,
    holm_adjust,
    rank_biserial_correlation,
    run_repeated_measures_anova,
    run_wilcoxon_pair,
)
from research.python.statistical_analysis.load import (
    load_statistical_inputs,
    require_ready_analytical_mart,
)
from research.python.statistical_analysis.prepare import (
    build_analysis_frame,
)
from research.python.statistical_analysis.validate import (
    validate_statistical_outputs,
    write_validation_report,
)


class StatisticalAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.real_inputs = load_statistical_inputs()
        cls.real_outputs = build_statistical_outputs(cls.real_inputs)

    def test_analysis_frame_keeps_all_planned_generations(self) -> None:
        frame = self.real_outputs["analysis_frame"]

        self.assertEqual(len(frame), 648)
        self.assertEqual(frame["generation_id"].nunique(), 648)
        self.assertEqual(frame["case_id"].nunique(), 36)

    def test_each_case_has_all_eighteen_conditions(self) -> None:
        frame = self.real_outputs["analysis_frame"]
        condition_counts = frame.groupby("case_id").size()

        self.assertTrue((condition_counts == 18).all())

    def test_primary_metric_preserves_unusable_zero_penalty(self) -> None:
        frame = self.real_outputs["analysis_frame"]
        unusable = frame.loc[frame["is_unusable"]]

        self.assertEqual(len(unusable), 10)
        self.assertTrue((unusable[PRIMARY_METRIC] == 0).all())

    def test_secondary_nulls_are_not_filled_with_zero(self) -> None:
        frame = self.real_outputs["analysis_frame"]
        unusable = frame.loc[frame["is_unusable"]]

        self.assertTrue(
            unusable["conservative_faithfulness"].isna().all()
        )
        self.assertTrue(
            unusable["verifiability"].isna().all()
        )

    def test_balanced_array_has_expected_shape(self) -> None:
        values, cases, models, evidence = build_balanced_array(
            self.real_outputs["analysis_frame"],
            PRIMARY_METRIC,
        )

        self.assertEqual(values.shape, (36, 3, 6))
        self.assertEqual(len(cases), 36)
        self.assertEqual(len(models), 3)
        self.assertEqual(len(evidence), 6)

    def test_missing_primary_cell_is_rejected(self) -> None:
        broken = self.real_outputs["analysis_frame"].copy()
        broken.loc[0, PRIMARY_METRIC] = np.nan

        with self.assertRaisesRegex(ValueError, "missing 1"):
            run_repeated_measures_anova(broken)

    def test_omnibus_has_three_valid_effects(self) -> None:
        omnibus = self.real_outputs["omnibus_tests"]

        self.assertEqual(len(omnibus), 3)
        self.assertEqual(
            set(omnibus["effect"]),
            {"model", "evidence", "model:evidence"},
        )
        self.assertTrue(
            omnibus["p_value_used"].between(0, 1).all()
        )
        self.assertTrue(
            omnibus["partial_eta_squared"].between(0, 1).all()
        )

    def test_paired_tests_have_thirty_three_planned_contrasts(self) -> None:
        paired = self.real_outputs["paired_tests"]

        self.assertEqual(len(paired), 33)
        self.assertEqual(
            int(
                (
                    paired["contrast_family"]
                    == "model_within_evidence"
                ).sum()
            ),
            18,
        )
        self.assertEqual(
            int(
                (
                    paired["contrast_family"]
                    == "evidence_vs_s0"
                ).sum()
            ),
            15,
        )

    def test_all_primary_comparisons_have_thirty_six_pairs(self) -> None:
        paired = self.real_outputs["paired_tests"]

        self.assertTrue((paired["planned_pair_count"] == 36).all())
        self.assertTrue((paired["observed_pair_count"] == 36).all())
        self.assertTrue((paired["excluded_pair_count"] == 0).all())

    def test_conditional_outputs_preserve_missing_pairs(self) -> None:
        paired = self.real_outputs["conditional_paired_tests"]

        self.assertEqual(len(paired), 99)
        self.assertTrue((paired["planned_pair_count"] == 36).all())
        self.assertTrue((paired["observed_pair_count"] <= 36).all())
        self.assertTrue((paired["observed_pair_count"] > 0).all())
        self.assertTrue(
            (
                paired["planned_pair_count"]
                == paired["observed_pair_count"]
                + paired["excluded_pair_count"]
            ).all()
        )

    def test_complete_case_sensitivity_uses_twenty_seven_cases(self) -> None:
        complete = self.real_outputs["complete_case_omnibus_tests"]

        self.assertEqual(len(complete), 3)
        self.assertEqual(set(complete["subject_count"]), {27})
        self.assertEqual(
            set(complete["metric_id"]),
            {"conservative_faithfulness"},
        )

    def test_unusable_generation_report_keeps_all_ten_s4_failures(self) -> None:
        failures = self.real_outputs["unusable_generations"]

        self.assertEqual(len(failures), 10)
        self.assertEqual(set(failures["evidence_level"]), {"S4"})
        self.assertTrue(
            failures["conservative_faithfulness"].isna().all()
        )
        self.assertTrue(
            (failures[PRIMARY_METRIC] == 0).all()
        )

    def test_pairing_uses_case_id_instead_of_row_order(self) -> None:
        frame = self.real_outputs["analysis_frame"]
        condition_a = frame.loc[
            (frame["model_id"] == "qwen3_8b")
            & (frame["evidence_level"] == "S1")
        ].sample(frac=1.0, random_state=1)
        condition_b = frame.loc[
            (frame["model_id"] == "deepseek_v4_flash")
            & (frame["evidence_level"] == "S1")
        ].sample(frac=1.0, random_state=2)

        shuffled = run_wilcoxon_pair(
            condition_a,
            condition_b,
            PRIMARY_METRIC,
        )
        ordered = run_wilcoxon_pair(
            condition_a.sort_values("case_id"),
            condition_b.sort_values("case_id"),
            PRIMARY_METRIC,
        )

        self.assertAlmostEqual(
            shuffled["mean_difference"],
            ordered["mean_difference"],
        )
        self.assertAlmostEqual(
            shuffled["raw_p_value"],
            ordered["raw_p_value"],
        )

    def test_all_zero_wilcoxon_difference_returns_one(self) -> None:
        condition = pd.DataFrame(
            {
                "case_id": [1, 2, 3],
                "metric": [0.2, 0.5, 0.9],
            }
        )

        result = run_wilcoxon_pair(
            condition,
            condition.copy(),
            "metric",
        )

        self.assertEqual(result["wilcoxon_statistic"], 0)
        self.assertEqual(result["raw_p_value"], 1)
        self.assertEqual(result["rank_biserial_correlation"], 0)

    def test_rank_biserial_has_expected_direction_and_bounds(self) -> None:
        positive = rank_biserial_correlation(
            np.array([1.0, 2.0, 3.0])
        )
        negative = rank_biserial_correlation(
            np.array([-1.0, -2.0, -3.0])
        )

        self.assertEqual(positive, 1.0)
        self.assertEqual(negative, -1.0)

    def test_holm_adjustment_matches_known_values(self) -> None:
        adjusted = holm_adjust(
            pd.Series([0.01, 0.04, 0.03])
        )

        np.testing.assert_allclose(
            adjusted.to_numpy(),
            np.array([0.03, 0.06, 0.06]),
            rtol=0.0,
            atol=1e-12,
        )

    def test_full_cohort_validation_passes(self) -> None:
        report = validate_statistical_outputs(
            self.real_outputs,
            self.real_inputs,
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["failed_check_count"], 0)
        self.assertEqual(report["exit_gate"], OUTPUT_EXIT_GATE)

    def test_duplicate_paired_contrast_fails_validation(self) -> None:
        broken_outputs = {
            key: value.copy()
            for key, value in self.real_outputs.items()
        }
        paired = broken_outputs["paired_tests"]
        paired.loc[1] = paired.loc[0]

        report = validate_statistical_outputs(
            broken_outputs,
            self.real_inputs,
        )

        self.assertFalse(report["passed"])
        self.assertGreater(
            report["checks"][
                "duplicate_paired_contrast_count"
            ]["observed"],
            0,
        )

    def test_analytical_mart_gate_is_required(self) -> None:
        invalid_report = {
            "passed": False,
            "failed_check_count": 1,
            "exit_gate": "METRICS_INVALID",
        }

        with self.assertRaisesRegex(
            ValueError,
            "ANALYTICAL_MART_READY",
        ):
            require_ready_analytical_mart(invalid_report)

    def test_outputs_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            analysis_path = root / "analysis_frame.csv"
            descriptive_path = root / "descriptive_statistics.csv"
            omnibus_path = root / "omnibus_tests.csv"
            paired_path = root / "paired_tests.csv"
            validation_path = root / "statistical_validation.json"

            with (
                patch.object(
                    build_module,
                    "OUTPUT_DIR",
                    root,
                ),
                patch.object(
                    build_module,
                    "ANALYSIS_FRAME_PATH",
                    analysis_path,
                ),
                patch.object(
                    build_module,
                    "DESCRIPTIVE_STATISTICS_PATH",
                    descriptive_path,
                ),
                patch.object(
                    build_module,
                    "OMNIBUS_TESTS_PATH",
                    omnibus_path,
                ),
                patch.object(
                    build_module,
                    "PAIRED_TESTS_PATH",
                    paired_path,
                ),
            ):
                write_statistical_outputs(self.real_outputs)

            report = validate_statistical_outputs(
                self.real_outputs,
                self.real_inputs,
            )
            write_validation_report(report, validation_path)

            self.assertTrue(analysis_path.is_file())
            self.assertTrue(descriptive_path.is_file())
            self.assertTrue(omnibus_path.is_file())
            self.assertTrue(paired_path.is_file())
            self.assertTrue(validation_path.is_file())

            saved_report = json.loads(
                validation_path.read_text(encoding="utf-8")
            )
            self.assertTrue(saved_report["passed"])

    def test_project_root_resolution_is_cwd_independent(self) -> None:
        project_root = find_project_root(Path(__file__))
        self.assertEqual(project_root, DEFAULT_PATHS.project_root)

        with tempfile.TemporaryDirectory() as temporary_dir:
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(project_root)

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from research.python.statistical_analysis.config "
                        "import PROJECT_ROOT; print(PROJECT_ROOT)"
                    ),
                ],
                cwd=temporary_dir,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertEqual(
            Path(result.stdout.strip()),
            project_root,
        )

    def test_expected_counts_match_core_design(self) -> None:
        self.assertEqual(EXPECTED_COUNTS["paired_tests"], 33)
        self.assertEqual(EXPECTED_COUNTS["omnibus_tests"], 3)


if __name__ == "__main__":
    unittest.main()
