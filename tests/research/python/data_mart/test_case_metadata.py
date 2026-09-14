from __future__ import annotations

import unittest

from research.python.data_mart.case_metadata import extract_case_metadata


class CaseMetadataTests(unittest.TestCase):
    def test_legacy_customer_envelope(self) -> None:
        value = extract_case_metadata({
            "package_id": "p1",
            "internal_metadata": {"customer": {
                "SK_ID_CURR": 123,
                "row_index": 7,
                "case_type": "near_threshold",
                "selection_rank": 2,
            }},
        })
        self.assertEqual(value.case_id, "123")
        self.assertEqual(value.source_kind, "customer")

    def test_freddie_case_envelope(self) -> None:
        value = extract_case_metadata({
            "package_id": "p2",
            "internal_metadata": {"case": {
                "case_id": "case_freddie_abc",
                "row_index": 11,
                "case_type": "true_positive",
                "selection_rank": 4,
            }},
        })
        self.assertEqual(value.case_id, "case_freddie_abc")
        self.assertEqual(value.selection_stratum, "true_positive")
        self.assertEqual(value.source_kind, "case")

    def test_conflicting_dual_identity_fails(self) -> None:
        with self.assertRaises(ValueError):
            extract_case_metadata({
                "package_id": "p3",
                "internal_metadata": {
                    "case": {"case_id": "A"},
                    "customer": {"SK_ID_CURR": "B"},
                },
            })

    def test_missing_identity_fails(self) -> None:
        with self.assertRaises(ValueError):
            extract_case_metadata({"package_id": "p4", "internal_metadata": {}})


if __name__ == "__main__":
    unittest.main()
