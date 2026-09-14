#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.python.datasets.receipts import load_receipt, sha256_path


def check(name, actual, expected):
    ok = actual == expected
    print(f"{'PASS' if ok else 'FAIL'} {name}: actual={actual!r} expected={expected!r}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Independently verify the Freddie 12m target artifacts.")
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument(
        "--expected",
        type=Path,
        default=REPO_ROOT / "config/research/datasets/freddie_sflld_2024_target_expected_v1.json",
    )
    args = parser.parse_args()

    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    manifest_path = args.target_dir / "freddie_target_12m_manifest_v1.json"
    receipt_path = args.target_dir / "freddie_sflld_2024_m12a_target_receipt_v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt = load_receipt(receipt_path)
    totals = manifest["totals"]

    checks = [
        check("raw_sha256", manifest["raw_source_sha256"], expected["raw_sha256"]),
        check("horizon_anchor", manifest["horizon_anchor"], "origination_first_payment_date"),
        check("raw_loan_age_used_for_horizon", manifest["raw_loan_age_used_for_horizon"], False),
        check("loans", totals["loans"], expected["loans"]),
        check("performance_rows", totals["performance_rows"], expected["performance_rows"]),
        check("eligible", totals["eligible"], expected["eligible"]),
        check("positive", totals["positive"], expected["positive"]),
        check("negative", totals["negative"], expected["negative"]),
        check("censored", totals["censored"], expected["censored"]),
        check("negative_plus_positive", totals["negative"] + totals["positive"], totals["eligible"]),
        check("eligible_plus_censored", totals["eligible"] + totals["censored"], totals["loans"]),
        check("partition_count", len(manifest["target_partitions"]), 4),
        check("event_counts", manifest["event_counts"], expected["event_counts"]),
        check("censor_reason_counts", manifest["censor_reason_counts"], expected["censor_reason_counts"]),
        check("receipt_status", receipt.status, "PASS"),
        check("receipt_manifest_hash", receipt.output_fingerprints[manifest_path.name], sha256_path(manifest_path)),
    ]

    independent = Counter()
    seen_ids: set[str] = set()
    duplicate_ids = 0
    partition_rows: dict[str, int] = {}
    quarter_stats_by_name = {item["quarter"]: item for item in manifest["quarter_stats"]}
    quarter_artifacts_by_name = {item["quarter"]: item for item in manifest["quarter_artifacts"]}
    for partition in manifest["target_partitions"]:
        quarter = partition["quarter"]
        path = args.target_dir / partition["filename"]
        expected_quarter = expected["quarters"][quarter]
        actual_quarter = quarter_stats_by_name[quarter]
        for field in ("loans", "eligible", "positive", "censored"):
            checks.append(check(f"quarter.{quarter}.{field}", actual_quarter[field], expected_quarter[field]))
        stats_artifact = quarter_artifacts_by_name[quarter]
        stats_path = args.target_dir / stats_artifact["stats_filename"]
        checks.append(check(f"quarter_stats_hash.{quarter}", stats_artifact["stats_sha256"], sha256_path(stats_path)))
        checks.append(check(f"receipt_quarter_stats_hash.{quarter}", receipt.output_fingerprints[stats_path.name], sha256_path(stats_path)))
        checks.append(check(f"partition_hash.{partition['quarter']}", partition["sha256"], sha256_path(path)))
        checks.append(check(f"receipt_partition_hash.{partition['quarter']}", receipt.output_fingerprints[path.name], sha256_path(path)))
        rows = 0
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows += 1
                loan_id = row["source_entity_id"]
                if loan_id in seen_ids:
                    duplicate_ids += 1
                else:
                    seen_ids.add(loan_id)
                status = row["target_observation_status"]
                if status == "ELIGIBLE":
                    independent["eligible"] += 1
                    if row["target"] == "1":
                        independent["positive"] += 1
                    elif row["target"] == "0":
                        independent["negative"] += 1
                    else:
                        independent["invalid_target"] += 1
                elif status == "CENSORED":
                    independent["censored"] += 1
                    if row["target"] not in ("", None):
                        independent["censored_with_target"] += 1
                else:
                    independent["invalid_status"] += 1
                if row["target"] == "1":
                    try:
                        event_index = int(row["event_payment_index"])
                    except ValueError:
                        independent["invalid_positive_event_index"] += 1
                    else:
                        if not 1 <= event_index <= 12:
                            independent["invalid_positive_event_index"] += 1
                if row["target_event"] == "no_serious_event_through_12m" and row["observed_horizon_months"] != "12":
                    independent["invalid_full_negative_horizon"] += 1
                if row["target_event"] == "voluntary_payoff_before_12m" and row["terminal_zero_balance_code"] != "01":
                    independent["invalid_payoff_code"] += 1
        partition_rows[partition["quarter"]] = rows
        checks.append(check(f"partition_rows.{partition['quarter']}", rows, partition["rows"]))

    independent["loans"] = sum(partition_rows.values())
    checks += [
        check("csv_loans", independent["loans"], totals["loans"]),
        check("csv_eligible", independent["eligible"], totals["eligible"]),
        check("csv_positive", independent["positive"], totals["positive"]),
        check("csv_negative", independent["negative"], totals["negative"]),
        check("csv_censored", independent["censored"], totals["censored"]),
        check("csv_invalid_target", independent["invalid_target"], 0),
        check("csv_censored_with_target", independent["censored_with_target"], 0),
        check("csv_invalid_status", independent["invalid_status"], 0),
        check("cross_partition_duplicate_ids", duplicate_ids, 0),
        check("invalid_positive_event_index", independent["invalid_positive_event_index"], 0),
        check("invalid_full_negative_horizon", independent["invalid_full_negative_horizon"], 0),
        check("invalid_payoff_code", independent["invalid_payoff_code"], 0),
    ]

    if all(checks):
        print("FREDDIE_SFLLD_M12A_TARGET=PASS")
        return 0
    print("FREDDIE_SFLLD_M12A_TARGET=FAIL")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
