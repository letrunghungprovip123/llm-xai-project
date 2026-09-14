"""Tests for the materialized generation metric table."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from research.python.common.paths import (
    DEFAULT_PATHS,
    find_project_root,
)
from research.python.metric_engineering import build as build_module
from research.python.metric_engineering import validate as validate_module
from research.python.metric_engineering.build import (
    build_generation_metrics,
    build_metric_outputs,
    write_metric_outputs,
)
from research.python.metric_engineering.config import (
    DERIVED_METRIC_COLUMNS,
    FINAL_EXIT_GATE,
)
from research.python.metric_engineering.efficiency import (
    add_efficiency_metrics,
)
from research.python.metric_engineering.load import (
    load_metric_inputs,
    require_ready_data_mart,
)
from research.python.metric_engineering.metric_dictionary import (
    build_metric_dictionary,
)
from research.python.metric_engineering.quality import (
    add_quality_metrics,
)
from research.python.metric_engineering.reliability import (
    add_reliability_metrics,
)
from research.python.metric_engineering.validate import (
    validate_metric_outputs,
    write_validation_report,
)


def make_generation_rows() -> pd.DataFrame:
    """Create small rows that exercise usable, unusable and zero denominator."""

    base = {
        "case_id": "case-1",
        "model_id": "model-1",
        "evidence_level": "S1",
        "package_id": "package-1",
        "selection_stratum": "low_risk",
        "model_order": 1,
        "evidence_order": 1,
        "case_order": 1,
        "runtime_status": "SUCCESS",
        "truncated_response": False,
        "raw_json_parse_success": True,
        "json_parse_success": True,
        "schema_valid": True,
        "usable": True,
        "retry_count": 0,
        "latency_ms": 2000,
        "input_token_count": 800,
        "output_token_count": 200,
        "total_token_count": 1000,
        "claim_count": 13,
        "supported_count": 8,
        "unsupported_count": 1,
        "contradicted_count": 1,
        "not_verifiable_count": 2,
        "not_applicable_count": 1,
        "resolved_count": 10,
        "applicable_count": 12,
    }

    usable = {
        **base,
        "generation_id": "generation-usable",
    }
    unusable = {
        **base,
        "generation_id": "generation-unusable",
        "case_id": "case-2",
        "package_id": "package-2",
        "case_order": 2,
        "truncated_response": True,
        "raw_json_parse_success": False,
        "json_parse_success": False,
        "schema_valid": False,
        "usable": False,
        "claim_count": 0,
        "supported_count": 0,
        "unsupported_count": 0,
        "contradicted_count": 0,
        "not_verifiable_count": 0,
        "not_applicable_count": 0,
        "resolved_count": 0,
        "applicable_count": 0,
    }
    no_applicable = {
        **base,
        "generation_id": "generation-no-applicable",
        "case_id": "case-3",
        "package_id": "package-3",
        "case_order": 3,
        "claim_count": 1,
        "supported_count": 0,
        "unsupported_count": 0,
        "contradicted_count": 0,
        "not_verifiable_count": 0,
        "not_applicable_count": 1,
        "resolved_count": 0,
        "applicable_count": 0,
    }

    return pd.DataFrame(
        [usable, unusable, no_applicable]
    )


class MetricEngineeringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.real_inputs = load_metric_inputs()
        cls.real_outputs = build_metric_outputs(cls.real_inputs)

    def test_resolved_faithfulness_excludes_nv_and_na(self) -> None:
        metrics = add_quality_metrics(make_generation_rows())
        usable = metrics.loc[
            metrics["generation_id"] == "generation-usable"
        ].iloc[0]

        self.assertAlmostEqual(
            usable["resolved_faithfulness"],
            8 / 10,
        )
        self.assertAlmostEqual(
            usable["verifiability"],
            10 / 12,
        )
        self.assertAlmostEqual(
            usable["conservative_faithfulness"],
            8 / 12,
        )

    def test_conservative_identity_holds(self) -> None:
        metrics = add_quality_metrics(make_generation_rows())
        usable = metrics.loc[
            metrics["generation_id"] == "generation-usable"
        ].iloc[0]

        product = (
            usable["resolved_faithfulness"]
            * usable["verifiability"]
        )
        self.assertAlmostEqual(
            usable["conservative_faithfulness"],
            product,
        )

    def test_unusable_generation_has_zero_yield_and_null_quality(self) -> None:
        metrics = add_quality_metrics(make_generation_rows())
        unusable = metrics.loc[
            metrics["generation_id"] == "generation-unusable"
        ].iloc[0]

        self.assertEqual(
            unusable["end_to_end_faithfulness_yield"],
            0,
        )
        self.assertTrue(
            pd.isna(unusable["resolved_faithfulness"])
        )
        self.assertTrue(
            pd.isna(unusable["verifiability"])
        )
        self.assertTrue(
            pd.isna(unusable["conservative_faithfulness"])
        )

    def test_zero_applicable_denominator_returns_null(self) -> None:
        metrics = add_quality_metrics(make_generation_rows())
        row = metrics.loc[
            metrics["generation_id"]
            == "generation-no-applicable"
        ].iloc[0]

        self.assertFalse(row["quality_metric_eligible"])
        self.assertTrue(pd.isna(row["verifiability"]))
        self.assertTrue(
            pd.isna(row["conservative_faithfulness"])
        )
        self.assertEqual(
            row["end_to_end_faithfulness_yield"],
            0,
        )

    def test_reliability_flags_are_component_based(self) -> None:
        metrics = add_reliability_metrics(
            make_generation_rows()
        )
        usable = metrics.iloc[0]
        unusable = metrics.iloc[1]

        self.assertTrue(usable["is_parse_success"])
        self.assertTrue(
            usable["is_strict_pipeline_success"]
        )
        self.assertTrue(unusable["is_unusable"])
        self.assertTrue(unusable["is_truncated"])
        self.assertFalse(
            unusable["is_strict_pipeline_success"]
        )

    def test_efficiency_metrics_do_not_create_infinity(self) -> None:
        rows = make_generation_rows()
        rows.loc[0, "latency_ms"] = 0
        rows.loc[0, "supported_count"] = 0

        metrics = add_efficiency_metrics(rows)
        numeric = metrics.select_dtypes(include=[np.number])

        self.assertEqual(
            int(np.isinf(numeric.to_numpy()).sum()),
            0,
        )
        self.assertTrue(
            pd.isna(metrics.loc[0, "output_tokens_per_second"])
        )
        self.assertTrue(
            pd.isna(
                metrics.loc[
                    0,
                    "latency_per_supported_claim_seconds",
                ]
            )
        )

    def test_metric_dictionary_covers_every_derived_column(self) -> None:
        dictionary = build_metric_dictionary()

        self.assertEqual(
            set(dictionary["metric_id"]),
            set(DERIVED_METRIC_COLUMNS),
        )
        self.assertFalse(
            dictionary["metric_id"].duplicated().any()
        )

    def test_full_cohort_build_keeps_all_planned_generations(self) -> None:
        metrics = self.real_outputs["generation_metrics"]

        self.assertEqual(len(metrics), 648)
        self.assertEqual(metrics["generation_id"].nunique(), 648)
        self.assertEqual(int(metrics["usable"].sum()), 638)
        self.assertEqual(int(metrics["is_unusable"].sum()), 10)

        cell_sizes = metrics.groupby(
            ["model_id", "evidence_level"]
        ).size()
        self.assertEqual(len(cell_sizes), 18)
        self.assertTrue((cell_sizes == 36).all())

    def test_full_cohort_validation_passes(self) -> None:
        report = validate_metric_outputs(
            self.real_outputs,
            self.real_inputs,
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["failed_check_count"], 0)
        self.assertEqual(report["exit_gate"], FINAL_EXIT_GATE)

    def test_duplicate_generation_metric_fails_validation(self) -> None:
        broken_outputs = {
            key: value.copy()
            for key, value in self.real_outputs.items()
        }
        duplicated = broken_outputs[
            "generation_metrics"
        ].copy()
        duplicated.loc[1, "generation_id"] = duplicated.loc[
            0,
            "generation_id",
        ]
        broken_outputs["generation_metrics"] = duplicated

        report = validate_metric_outputs(
            broken_outputs,
            self.real_inputs,
        )

        self.assertFalse(report["passed"])
        self.assertGreater(
            report["checks"][
                "duplicate_generation_metric_id_count"
            ]["observed"],
            0,
        )

    def test_invalid_metric_formula_fails_validation(self) -> None:
        broken_outputs = {
            key: value.copy()
            for key, value in self.real_outputs.items()
        }
        broken_outputs["generation_metrics"].loc[
            0,
            "resolved_faithfulness",
        ] = 1.5

        report = validate_metric_outputs(
            broken_outputs,
            self.real_inputs,
        )

        self.assertFalse(report["passed"])
        self.assertGreater(
            report["checks"][
                "resolved_faithfulness_formula_mismatch_count"
            ]["observed"],
            0,
        )
        self.assertGreater(
            report["checks"]["rate_out_of_bounds_count"][
                "observed"
            ],
            0,
        )

    def test_data_mart_gate_is_required(self) -> None:
        invalid_report = {
            "passed": False,
            "failed_check_count": 1,
            "exit_gate": "DATA_MART_INVALID",
        }

        with self.assertRaisesRegex(
            ValueError,
            "DATA_MART_READY",
        ):
            require_ready_data_mart(invalid_report)

    def test_outputs_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            generation_path = root / "generation_metrics.csv"
            dictionary_path = root / "metric_dictionary.csv"
            validation_path = root / "metric_validation.json"

            with (
                patch.object(
                    build_module,
                    "GENERATION_METRICS_PATH",
                    generation_path,
                ),
                patch.object(
                    build_module,
                    "METRIC_DICTIONARY_PATH",
                    dictionary_path,
                ),
            ):
                write_metric_outputs(self.real_outputs)

            report = validate_metric_outputs(
                self.real_outputs,
                self.real_inputs,
            )
            write_validation_report(report, validation_path)

            self.assertTrue(generation_path.is_file())
            self.assertTrue(dictionary_path.is_file())
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
                        "from research.python.metric_engineering.config "
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

    def test_generation_metric_output_has_stable_columns(self) -> None:
        metrics = build_generation_metrics(
            self.real_inputs["generations"]
        )

        self.assertEqual(metrics.columns[0], "metric_engineering_version")
        self.assertEqual(metrics.columns[1], "generation_id")
        self.assertIn("resolved_faithfulness", metrics.columns)
        self.assertIn(
            "supported_claims_per_1000_total_tokens",
            metrics.columns,
        )


if __name__ == "__main__":
    unittest.main()
