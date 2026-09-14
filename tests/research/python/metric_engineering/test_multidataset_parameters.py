from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from research.python.metric_engineering.load import load_metric_inputs
from research.python.metric_engineering.validate import validate_metric_outputs
from research.python.metric_engineering.build import build_metric_outputs


class MetricParameterTests(unittest.TestCase):
    def test_explicit_input_paths_and_counts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            generations = pd.DataFrame([
                {
                    "generation_id": "g1", "case_id": "c1", "model_id": "m1",
                    "evidence_level": "S0", "package_id": "p1", "selection_stratum": "x",
                    "model_order": 0, "evidence_order": 0, "case_order": 0,
                    "runtime_status": "SUCCESS", "runtime_error_type": None,
                    "runtime_error_message": None, "truncated_response": False,
                    "raw_json_parse_success": True, "json_parse_success": True,
                    "schema_valid": True, "usable": True, "retry_count": 0,
                    "latency_ms": 100.0, "input_token_count": 10, "output_token_count": 10,
                    "total_token_count": 20, "claim_count": 1, "supported_count": 1,
                    "unsupported_count": 0, "contradicted_count": 0,
                    "not_verifiable_count": 0, "not_applicable_count": 0,
                    "resolved_count": 1, "applicable_count": 1,
                }
            ])
            claims = pd.DataFrame([{"claim_id": "x", "generation_id": "g1", "validation_status": "SUPPORTED"}])
            generations.to_csv(root / "generations.csv", index=False)
            claims.to_csv(root / "claims.csv", index=False)
            (root / "validation.json").write_text(
                '{"passed":true,"failed_check_count":0,"exit_gate":"DATA_MART_READY"}\n'
            )
            inputs = load_metric_inputs({
                "data_mart_validation": root / "validation.json",
                "generations": root / "generations.csv",
                "claims": root / "claims.csv",
            })
            outputs = build_metric_outputs(inputs)
            report = validate_metric_outputs(outputs, inputs, expected_counts={
                "generations": 1, "usable_generations": 1, "unusable_generations": 0,
                "claims": 1, "models": 1, "evidence_levels": 1,
                "model_evidence_cells": 1, "generations_per_model_evidence_cell": 1,
            })
            self.assertTrue(report["passed"], report)


if __name__ == "__main__":
    unittest.main()
