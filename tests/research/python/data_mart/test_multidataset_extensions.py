from __future__ import annotations

import unittest

import pandas as pd

from research.python.data_mart.build import CLAIM_TYPES, _build_claim_aggregates


class MultiDatasetDataMartTests(unittest.TestCase):
    def test_default_claim_types_remain_historical(self) -> None:
        self.assertNotIn("causal", CLAIM_TYPES)

    def test_explicit_causal_aggregate_is_available(self) -> None:
        claims = pd.DataFrame([
            {
                "generation_id": "g1",
                "claim_id": "c1",
                "claim_type": "causal",
                "is_supported": True,
                "is_unsupported": False,
                "is_contradicted": False,
                "is_not_verifiable": False,
                "is_not_applicable": False,
                "is_resolved": True,
                "is_applicable": True,
                "is_semantic_unresolved": False,
                "is_policy_violation": False,
            }
        ])
        result = _build_claim_aggregates(
            claims,
            claim_types=(*CLAIM_TYPES, "causal"),
        )
        self.assertEqual(int(result.loc[0, "causal_claim_count"]), 1)


if __name__ == "__main__":
    unittest.main()
