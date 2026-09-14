#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.python.datasets.receipts import load_receipt, sha256_path


def _pass(name: str, actual, expected) -> bool:
    ok = actual == expected
    print(f"{'PASS' if ok else 'FAIL'} {name}: actual={actual!r} expected={expected!r}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Freddie M11 raw intake against the frozen raw-source baseline.")
    parser.add_argument("--raw-zip", required=True, type=Path)
    parser.add_argument("--intake-dir", required=True, type=Path)
    parser.add_argument(
        "--expected",
        type=Path,
        default=REPO_ROOT / "config/research/datasets/freddie_sflld_2024_intake_expected_v1.json",
    )
    args = parser.parse_args()
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    audit_path = args.intake_dir / "freddie_sflld_2024_intake_audit_v1.json"
    manifest_path = args.intake_dir / "freddie_sflld_2024_raw_manifest_v1.json"
    receipt_path = args.intake_dir / "freddie_sflld_2024_m11_receipt_v1.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt = load_receipt(receipt_path)

    checks = [
        _pass("raw_sha256", sha256_path(args.raw_zip), expected["raw_sha256"]),
        _pass("manifest_raw_sha256", manifest["source"]["sha256"], expected["raw_sha256"]),
        _pass("quarter_count", manifest["layout"]["quarter_count"], 4),
        _pass("origination_width", manifest["layout"]["origination_width"], expected["origination_width"]),
        _pass("performance_width", manifest["layout"]["performance_width"], expected["performance_width"]),
        _pass("origination_rows", audit["totals"]["origination_rows"], expected["origination_rows"]),
        _pass("performance_rows", audit["totals"]["performance_rows"], expected["performance_rows"]),
        _pass("max_reporting_period", audit["totals"]["max_reporting_period"], expected["max_reporting_period"]),
        _pass("malformed_rows", audit["totals"]["malformed_rows"], 0),
        _pass("duplicate_origination_ids", audit["totals"]["duplicate_origination_loan_ids"], 0),
        _pass("performance_orphan_rows", audit["totals"]["performance_orphan_rows"], 0),
        _pass("origination_ids_without_performance", audit["totals"]["origination_ids_without_performance"], 0),
        _pass("receipt_status", receipt.status, "PASS"),
        _pass("receipt_dataset_id", receipt.dataset_id, "freddie_sflld_2024"),
        _pass("receipt_manifest_hash", receipt.output_fingerprints[manifest_path.name], sha256_path(manifest_path)),
        _pass("receipt_audit_hash", receipt.output_fingerprints[audit_path.name], sha256_path(audit_path)),
    ]
    if all(checks):
        print("FREDDIE_SFLLD_M11=PASS")
        return 0
    print("FREDDIE_SFLLD_M11=FAIL")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
