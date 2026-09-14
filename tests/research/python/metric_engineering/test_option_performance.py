from __future__ import annotations

import unittest

import pandas as pd

from scripts.research.freddie_m22_metrics_0023 import build_option_performance, validate_options


class OptionPerformanceTests(unittest.TestCase):
    def test_primary_mean_keeps_planned_zero_row(self) -> None:
        frame = pd.DataFrame([
            {
                "model_order": 0, "model_id": "m", "evidence_order": 1,
                "evidence_level": "S1", "usable": True,
                "end_to_end_faithfulness_yield": 1.0,
                "resolved_faithfulness": 1.0, "verifiability": 1.0,
                "conservative_faithfulness": 1.0, "claim_count": 1,
                "supported_count": 1, "unsupported_count": 0,
                "contradicted_count": 0, "not_verifiable_count": 0,
                "not_applicable_count": 0, "resolved_count": 1,
                "applicable_count": 1, "latency_seconds": 1.0,
                "total_token_count": 10, "supported_claims_per_1000_total_tokens": 100.0,
            },
            {
                "model_order": 0, "model_id": "m", "evidence_order": 1,
                "evidence_level": "S1", "usable": False,
                "end_to_end_faithfulness_yield": 0.0,
                "resolved_faithfulness": None, "verifiability": None,
                "conservative_faithfulness": None, "claim_count": 0,
                "supported_count": 0, "unsupported_count": 0,
                "contradicted_count": 0, "not_verifiable_count": 0,
                "not_applicable_count": 0, "resolved_count": 0,
                "applicable_count": 0, "latency_seconds": 1.0,
                "total_token_count": 10, "supported_claims_per_1000_total_tokens": 0.0,
            },
        ])
        options = build_option_performance(frame)
        self.assertAlmostEqual(options.loc[0, "mean_end_to_end_faithfulness_yield"], 0.5)
        self.assertEqual(int(options.loc[0, "planned_generation_count"]), 2)
        self.assertEqual(int(options.loc[0, "resolved_faithfulness_n"]), 1)
        report = validate_options(options, {
            "model_evidence_cells": 1,
            "generations_per_model_evidence_cell": 2,
        })
        self.assertTrue(report["passed"], report)


if __name__ == "__main__":
    unittest.main()
