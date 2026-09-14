from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from research.python.datasets.freddie_sflld.raw_intake import FreddieRawIntakeAuditor
from research.python.datasets.freddie_sflld.schema import ORIGINATION_WIDTH, PERFORMANCE_WIDTH
from research.python.datasets.receipts import load_receipt, sha256_path


def _row(width: int, overrides: dict[int, str]) -> str:
    values = [""] * width
    for index, value in overrides.items():
        values[index] = value
    return "|".join(values) + "\n"


def _build_nested(quarter: str) -> bytes:
    out = io.BytesIO()
    qnum = quarter[-1]
    loan = f"F24Q{qnum}0000001"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"orig_{quarter}.txt",
            _row(ORIGINATION_WIDTH, {19: loan, 0: "750", 30: "9999"}),
        )
        archive.writestr(
            f"perf_{quarter}.txt",
            _row(PERFORMANCE_WIDTH, {0: loan, 1: "202401", 3: "00", 4: "0"}),
        )
    return out.getvalue()


class FreddieRawIntakeTests(unittest.TestCase):
    def test_four_quarter_fixture_is_audited_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "historical_data_2024.zip"
            with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_STORED) as archive:
                for quarter in ("2024Q1", "2024Q2", "2024Q3", "2024Q4"):
                    archive.writestr(f"historical_data_{quarter}.zip", _build_nested(quarter))
            out1 = root / "out1"
            out2 = root / "out2"
            r1 = FreddieRawIntakeAuditor(raw).run(out1)
            r2 = FreddieRawIntakeAuditor(raw).run(out2)
            self.assertEqual(r1.audit["totals"]["origination_rows"], 4)
            self.assertEqual(r1.audit["totals"]["performance_rows"], 4)
            self.assertEqual(r1.audit, r2.audit)
            self.assertEqual(r1.manifest, r2.manifest)
            self.assertEqual(sha256_path(r1.manifest_path), sha256_path(r2.manifest_path))
            receipt = load_receipt(r1.receipt_path)
            self.assertEqual(receipt.status, "PASS")

    def test_orphan_performance_id_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "historical_data_2024.zip"
            with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_STORED) as archive:
                for quarter in ("2024Q1", "2024Q2", "2024Q3", "2024Q4"):
                    nested = io.BytesIO()
                    qnum = quarter[-1]
                    good = f"F24Q{qnum}0000001"
                    bad = f"F24Q{qnum}9999999"
                    with zipfile.ZipFile(nested, "w", compression=zipfile.ZIP_DEFLATED) as z:
                        z.writestr(f"orig_{quarter}.txt", _row(ORIGINATION_WIDTH, {19: good}))
                        z.writestr(f"perf_{quarter}.txt", _row(PERFORMANCE_WIDTH, {0: bad, 1: "202401"}))
                    archive.writestr(f"historical_data_{quarter}.zip", nested.getvalue())
            with self.assertRaises(ValueError):
                FreddieRawIntakeAuditor(raw).run(root / "out")


if __name__ == "__main__":
    unittest.main()
