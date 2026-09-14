from __future__ import annotations

import unittest

import pandas as pd

from research.python.data_mart.build import CLAIM_TYPES, _build_claim_aggregates


class FreddieClaimTypeAggregateTests(unittest.TestCase):
    def test_causal_can_be_opted_in_without_changing_legacy_default(self) -> None:
        frame = pd.DataFrame([
            {"generation_id": "g1", "claim_id": "c1", "claim_type": "prediction", "is_supported": True, "is_unsupported": False, "is_contradicted": False, "is_not_verifiable": False, "is_not_applicable": False, "is_resolved": True, "is_applicable": True, "is_semantic_unresolved": False, "is_policy_violation": False},
            {"generation_id": "g1", "claim_id": "c2", "claim_type": "causal", "is_supported": False, "is_unsupported": True, "is_contradicted": False, "is_not_verifiable": False, "is_not_applicable": False, "is_resolved": True, "is_applicable": True, "is_semantic_unresolved": False, "is_policy_violation": True},
        ])
        legacy = _build_claim_aggregates(frame)
        self.assertNotIn("causal_claim_count", legacy.columns)
        extended = _build_claim_aggregates(frame, claim_types=(*CLAIM_TYPES, "causal"))
        self.assertEqual(int(extended.loc[0, "causal_claim_count"]), 1)
        self.assertEqual(int(extended.loc[0, "claim_count"]), 2)


if __name__ == "__main__":
    unittest.main()
