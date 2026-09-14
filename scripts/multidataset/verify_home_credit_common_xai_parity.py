#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare common-XAI Home Credit outputs with frozen legacy XAI quality truths.")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--historical-root", type=Path, required=True)
    parser.add_argument("--metric-tolerance", type=float, default=1e-6)
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()
    historical = args.historical_root.expanduser().resolve()
    new_manifest_path = workspace / "data/manifests/common_xai_manifest.json"
    old_manifest_path = historical / "data/manifests/xai_evidence_quality_manifest.json"
    if not new_manifest_path.is_file():
        raise FileNotFoundError(new_manifest_path)
    if not old_manifest_path.is_file():
        raise FileNotFoundError(old_manifest_path)
    new = read_json(new_manifest_path)
    old = read_json(old_manifest_path).get("aggregate_summary", {})

    failures: list[str] = []
    def exact(name, actual, expected):
        ok = actual == expected
        print(("PASS" if ok else "FAIL"), f"{name}: actual={actual!r} expected={expected!r}")
        if not ok:
            failures.append(name)

    def close(name, actual, expected, tol=args.metric_tolerance):
        actual = float(actual)
        expected = float(expected)
        delta = abs(actual - expected)
        ok = delta <= tol
        print(("PASS" if ok else "FAIL"), f"{name}: actual={actual:.12g} expected={expected:.12g} delta={delta:.3g} tol={tol:g}")
        if not ok:
            failures.append(name)

    exact("dataset_id", new.get("dataset_id"), "home_credit_default_risk")
    exact("case_count", int(new.get("case_count", -1)), int(old.get("case_count", -2)))
    exact("feature_count", int(new.get("feature_count", -1)), int(old.get("feature_count", -2)))
    exact("failed_additivity_count", int(new.get("additivity", {}).get("failed_count", -1)), int(old.get("additivity", {}).get("failed_additivity_count", -2)))
    close("mean_top10_coverage", new["quality"]["mean_top10_coverage"], old["topk_coverage"]["mean_top10_coverage"])
    close("mean_comprehensiveness_top10", new["quality"]["mean_comprehensiveness_top10"], old["comprehensiveness"]["mean_comprehensiveness_top10"])
    close("mean_sufficiency_drop_top10", new["quality"]["mean_sufficiency_drop_top10"], old["sufficiency"]["mean_sufficiency_drop_top10"])
    close("unknown_feature_group_abs_share_mean", new["quality"]["unknown_feature_group_abs_share_mean"], old["concept_accounting"]["mean_unknown_feature_group_abs_share"])

    old_cases = historical / "data/reports/xai/xai_selected_cases.csv"
    new_cases = workspace / "data/reports/xai/xai_selected_cases.csv"
    if old_cases.is_file() and new_cases.is_file():
        old_df = pd.read_csv(old_cases)
        new_df = pd.read_csv(new_cases)
        if "SK_ID_CURR" in old_df.columns and "source_entity_id" in new_df.columns:
            old_ids = old_df["SK_ID_CURR"].map(lambda v: str(int(v)) if pd.notna(v) else "").tolist()
            new_ids = new_df["source_entity_id"].map(str).tolist()
            exact("selected_case_identity_order", new_ids, old_ids)
        if "case_type" in old_df.columns and "case_type" in new_df.columns:
            exact("selected_case_type_order", new_df["case_type"].astype(str).tolist(), old_df["case_type"].astype(str).tolist())
    else:
        print("SKIP selected_case_identity_order: historical selected-case CSV unavailable")

    if failures:
        print("HOME_CREDIT_COMMON_XAI_PARITY=FAIL")
        print("Failed checks:", ", ".join(failures))
        return 1
    print("HOME_CREDIT_COMMON_XAI_PARITY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
