from __future__ import annotations

import csv
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import pandas as pd

from ..common.hashing import sha256_file
from ..common.paths import DEFAULT_PATHS, create_directories


PROJECT_ROOT = DEFAULT_PATHS.project_root
RAW_DIR = DEFAULT_PATHS.raw_dir
REPORT_DIR = DEFAULT_PATHS.report_dir
MANIFEST_DIR = DEFAULT_PATHS.manifest_dir

REQUIRED_FILES = [
    "application_train.csv",
    "bureau.csv",
    "bureau_balance.csv",
    "previous_application.csv",
    "installments_payments.csv",
    "POS_CASH_balance.csv",
    "credit_card_balance.csv",
]

OPTIONAL_FILES = [
    "application_test.csv",
    "sample_submission.csv",
    "HomeCredit_columns_description.csv",
]

RELATIONSHIPS = [
    {
        "name": "application_train -> bureau",
        "parent_file": "application_train.csv",
        "child_file": "bureau.csv",
        "parent_key": "SK_ID_CURR",
        "child_key": "SK_ID_CURR",
        "aggregation_level": "SK_ID_CURR",
    },
    {
        "name": "bureau -> bureau_balance",
        "parent_file": "bureau.csv",
        "child_file": "bureau_balance.csv",
        "parent_key": "SK_ID_BUREAU",
        "child_key": "SK_ID_BUREAU",
        "aggregation_level": "SK_ID_CURR via bureau.SK_ID_BUREAU",
    },
    {
        "name": "application_train -> previous_application",
        "parent_file": "application_train.csv",
        "child_file": "previous_application.csv",
        "parent_key": "SK_ID_CURR",
        "child_key": "SK_ID_CURR",
        "aggregation_level": "SK_ID_CURR",
    },
    {
        "name": "previous_application -> installments_payments",
        "parent_file": "previous_application.csv",
        "child_file": "installments_payments.csv",
        "parent_key": "SK_ID_PREV",
        "child_key": "SK_ID_PREV",
        "aggregation_level": "SK_ID_CURR via SK_ID_PREV",
    },
    {
        "name": "previous_application -> POS_CASH_balance",
        "parent_file": "previous_application.csv",
        "child_file": "POS_CASH_balance.csv",
        "parent_key": "SK_ID_PREV",
        "child_key": "SK_ID_PREV",
        "aggregation_level": "SK_ID_CURR via SK_ID_PREV",
    },
    {
        "name": "previous_application -> credit_card_balance",
        "parent_file": "previous_application.csv",
        "child_file": "credit_card_balance.csv",
        "parent_key": "SK_ID_PREV",
        "child_key": "SK_ID_PREV",
        "aggregation_level": "SK_ID_CURR via SK_ID_PREV",
    },
]


def count_csv_rows_columns(path: Path) -> tuple[int, int]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        row_count = sum(1 for _ in reader)
    return row_count, len(header)


def read_columns(path: Path) -> list[str]:
    return pd.read_csv(path, nrows=0).columns.tolist()


def step_0_verify_raw_files() -> dict:
    manifest = {
        "dataset_name": "home_credit_default_risk",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "raw_dir": str(RAW_DIR.relative_to(PROJECT_ROOT)),
        "raw_files": {},
        "optional_files": {},
        "status": "unknown",
        "errors": [],
    }

    for filename in REQUIRED_FILES:
        path = RAW_DIR / filename
        item = {
            "path": str(path.relative_to(PROJECT_ROOT)),
            "exists": path.exists(),
            "rows": None,
            "columns": None,
            "size_mb": None,
            "sha256": None,
            "readable": False,
        }

        if not path.exists():
            manifest["errors"].append(f"Missing required file: {filename}")
            manifest["raw_files"][filename] = item
            continue

        try:
            rows, cols = count_csv_rows_columns(path)
            item["rows"] = rows
            item["columns"] = cols
            item["size_mb"] = round(path.stat().st_size / (1024 * 1024), 2)
            item["sha256"] = sha256_file(path)
            item["readable"] = True
        except Exception as e:
            manifest["errors"].append(f"Cannot read {filename}: {e}")

        manifest["raw_files"][filename] = item

    for filename in OPTIONAL_FILES:
        path = RAW_DIR / filename
        manifest["optional_files"][filename] = {
            "path": str(path.relative_to(PROJECT_ROOT)),
            "exists": path.exists(),
            "size_mb": round(path.stat().st_size / (1024 * 1024), 2) if path.exists() else None,
        }

    required_ok = all(
        manifest["raw_files"][f]["exists"] and manifest["raw_files"][f]["readable"]
        for f in REQUIRED_FILES
    )

    manifest["status"] = "raw_verified" if required_ok else "blocked"

    out_path = MANIFEST_DIR / "raw_file_manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return manifest


def profile_csv_file(path: Path, chunksize: int = 200_000) -> dict:
    columns = read_columns(path)

    missing_counts = defaultdict(int)
    non_null_counts = defaultdict(int)
    sample_values = defaultdict(list)
    dtype_seen = defaultdict(set)
    total_rows = 0

    duplicate_hashes = set()
    duplicate_rows = 0

    for chunk in pd.read_csv(path, chunksize=chunksize, low_memory=False):
        total_rows += len(chunk)

        for col in chunk.columns:
            missing_counts[col] += int(chunk[col].isna().sum())
            non_null_counts[col] += int(chunk[col].notna().sum())
            dtype_seen[col].add(str(chunk[col].dtype))

            if len(sample_values[col]) < 5:
                values = chunk[col].dropna().astype(str).head(5).tolist()
                for v in values:
                    if v not in sample_values[col] and len(sample_values[col]) < 5:
                        sample_values[col].append(v)

        row_hashes = pd.util.hash_pandas_object(chunk, index=False).astype(str)
        for h in row_hashes:
            if h in duplicate_hashes:
                duplicate_rows += 1
            else:
                duplicate_hashes.add(h)

    unique_counts = {}
    for col in columns:
        unique_values = set()
        for chunk in pd.read_csv(path, usecols=[col], chunksize=chunksize, low_memory=False):
            unique_values.update(chunk[col].dropna().astype(str).unique().tolist())
        unique_counts[col] = len(unique_values)

    column_profiles = []
    for col in columns:
        missing = missing_counts[col]
        missing_pct = round(missing / total_rows * 100, 4) if total_rows else None
        column_profiles.append(
            {
                "column": col,
                "dtype_seen": sorted(dtype_seen[col]),
                "missing_count": missing,
                "missing_percentage": missing_pct,
                "non_null_count": non_null_counts[col],
                "unique_values": unique_counts[col],
                "sample_values": sample_values[col],
            }
        )

    return {
        "file": path.name,
        "row_count": total_rows,
        "column_count": len(columns),
        "columns": columns,
        "duplicate_rows_estimated_by_hash": duplicate_rows,
        "memory_usage_file_size_mb": round(path.stat().st_size / (1024 * 1024), 2),
        "column_profiles": column_profiles,
    }


def step_1_raw_schema_audit() -> dict:
    results = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tables": {},
        "key_checks": {},
        "status": "unknown",
        "errors": [],
    }

    summary_rows = []

    key_expectations = {
        "application_train.csv": ["SK_ID_CURR", "TARGET"],
        "bureau.csv": ["SK_ID_CURR", "SK_ID_BUREAU"],
        "bureau_balance.csv": ["SK_ID_BUREAU"],
        "previous_application.csv": ["SK_ID_CURR", "SK_ID_PREV"],
        "installments_payments.csv": ["SK_ID_CURR", "SK_ID_PREV"],
        "POS_CASH_balance.csv": ["SK_ID_CURR", "SK_ID_PREV"],
        "credit_card_balance.csv": ["SK_ID_CURR", "SK_ID_PREV"],
    }

    for filename in REQUIRED_FILES:
        path = RAW_DIR / filename
        if not path.exists():
            results["errors"].append(f"Missing file for schema audit: {filename}")
            continue

        print(f"[Step 1] Profiling {filename} ...")
        profile = profile_csv_file(path)
        results["tables"][filename] = profile

        columns = set(profile["columns"])
        expected_keys = key_expectations.get(filename, [])
        missing_keys = [k for k in expected_keys if k not in columns]

        results["key_checks"][filename] = {
            "expected_keys": expected_keys,
            "missing_keys": missing_keys,
            "passed": len(missing_keys) == 0,
        }

        for col_profile in profile["column_profiles"]:
            summary_rows.append(
                {
                    "table": filename,
                    "column": col_profile["column"],
                    "dtype_seen": "|".join(col_profile["dtype_seen"]),
                    "missing_count": col_profile["missing_count"],
                    "missing_percentage": col_profile["missing_percentage"],
                    "unique_values": col_profile["unique_values"],
                    "sample_values": "|".join(col_profile["sample_values"]),
                }
            )

    pd.DataFrame(summary_rows).to_csv(REPORT_DIR / "raw_schema_summary.csv", index=False)

    md_lines = []
    md_lines.append("# Raw Schema Audit Report\n")
    md_lines.append(f"Created at: `{results['created_at']}`\n")

    for filename, profile in results["tables"].items():
        md_lines.append(f"## {filename}\n")
        md_lines.append(f"- Rows: `{profile['row_count']}`")
        md_lines.append(f"- Columns: `{profile['column_count']}`")
        md_lines.append(f"- Duplicate rows estimated by hash: `{profile['duplicate_rows_estimated_by_hash']}`")
        md_lines.append(f"- File size MB: `{profile['memory_usage_file_size_mb']}`")
        key_check = results["key_checks"].get(filename, {})
        md_lines.append(f"- Expected keys: `{key_check.get('expected_keys')}`")
        md_lines.append(f"- Missing keys: `{key_check.get('missing_keys')}`")
        md_lines.append("")

    md_lines.append("## Notes\n")
    md_lines.append("- Missing percentage, dtype, unique values, and sample values are saved in `raw_schema_summary.csv`.")
    md_lines.append("- Raw files were only read, not modified.")

    (REPORT_DIR / "raw_schema_audit_report.md").write_text("\n".join(md_lines), encoding="utf-8")

    all_key_checks_pass = all(v["passed"] for v in results["key_checks"].values())
    results["status"] = "schema_audit_passed" if all_key_checks_pass and not results["errors"] else "blocked"

    return results


def load_key_series(filename: str, key: str) -> pd.Series:
    path = RAW_DIR / filename
    return pd.read_csv(path, usecols=[key])[key]


def relationship_basic_stats(parent_file: str, child_file: str, parent_key: str, child_key: str) -> dict:
    parent = load_key_series(parent_file, parent_key).dropna()
    child = load_key_series(child_file, child_key).dropna()

    parent_set = set(parent.unique())
    child_counts = child.value_counts()

    matched_keys = set(child_counts.index).intersection(parent_set)
    unmatched_child_keys = set(child_counts.index).difference(parent_set)

    parent_with_child = parent[parent.isin(matched_keys)].nunique()
    parent_total = parent.nunique()
    parent_without_child = parent_total - parent_with_child

    records_per_parent = child_counts[child_counts.index.isin(parent_set)]

    return {
        "parent_file": parent_file,
        "child_file": child_file,
        "parent_key": parent_key,
        "child_key": child_key,
        "parent_unique_keys": int(parent_total),
        "child_rows": int(len(child)),
        "child_unique_keys": int(child.nunique()),
        "parent_with_child_history": int(parent_with_child),
        "parent_without_child_history": int(parent_without_child),
        "unmatched_child_key_count": int(len(unmatched_child_keys)),
        "avg_records_per_parent_with_history": float(round(records_per_parent.mean(), 4)) if len(records_per_parent) else 0.0,
        "max_records_per_parent": int(records_per_parent.max()) if len(records_per_parent) else 0,
        "raw_merge_would_create_row_explosion": True,
        "aggregation_required": True,
    }


def step_2_relationship_audit() -> dict:
    results = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "relationships": [],
        "status": "unknown",
        "errors": [],
    }

    for rel in RELATIONSHIPS:
        print(f"[Step 2] Auditing relationship: {rel['name']} ...")
        try:
            stats = relationship_basic_stats(
                rel["parent_file"],
                rel["child_file"],
                rel["parent_key"],
                rel["child_key"],
            )
            stats["name"] = rel["name"]
            stats["aggregation_level"] = rel["aggregation_level"]
            results["relationships"].append(stats)
        except Exception as e:
            results["errors"].append(f"{rel['name']}: {e}")

    md_lines = []
    md_lines.append("# Relationship Audit Report\n")
    md_lines.append(f"Created at: `{results['created_at']}`\n")
    md_lines.append("## Relationship Summary\n")
    md_lines.append("| Relationship | Parent | Child | Join Key | Avg child records | Max child records | Parent without history | Unmatched child keys | Aggregation required |")
    md_lines.append("|---|---|---|---:|---:|---:|---:|---:|---|")

    for r in results["relationships"]:
        md_lines.append(
            f"| {r['name']} | {r['parent_file']} | {r['child_file']} | "
            f"{r['child_key']} | {r['avg_records_per_parent_with_history']} | "
            f"{r['max_records_per_parent']} | {r['parent_without_child_history']} | "
            f"{r['unmatched_child_key_count']} | yes |"
        )

    md_lines.append("\n## Main Conclusion\n")
    md_lines.append(
        "All auxiliary tables are many-to-one or many-to-many relative to `application_train`. "
        "Therefore, raw auxiliary tables must not be directly merged into `application_train`. "
        "Each auxiliary table must first be aggregated to one row per `SK_ID_CURR` before building the final feature matrix."
    )
    md_lines.append("\n## Final Rule\n")
    md_lines.append("The final feature matrix must contain exactly one row per `SK_ID_CURR`.")

    if results["errors"]:
        md_lines.append("\n## Errors\n")
        for err in results["errors"]:
            md_lines.append(f"- {err}")

    (REPORT_DIR / "relationship_audit_report.md").write_text("\n".join(md_lines), encoding="utf-8")

    results["status"] = "relationship_audit_passed" if not results["errors"] else "blocked"

    return results


def write_batch_summary(step0: dict, step1: dict, step2: dict) -> None:
    completed = 0
    total_technical_steps = 20

    step_statuses = [
        ("Step 0", "Verify raw files", step0["status"]),
        ("Step 1", "Raw schema audit", step1["status"]),
        ("Step 2", "Relationship audit", step2["status"]),
    ]

    passed_statuses = {
        "raw_verified",
        "schema_audit_passed",
        "relationship_audit_passed",
    }

    for _, _, status in step_statuses:
        if status in passed_statuses:
            completed += 1

    remaining = total_technical_steps - completed

    summary = {
        "batch_name": "batch_1_raw_to_relationship_audit",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "technical_steps_completed": completed,
        "technical_steps_total": total_technical_steps,
        "technical_steps_remaining": remaining,
        "step_statuses": [
            {"step": s, "name": n, "status": st}
            for s, n, st in step_statuses
        ],
        "next_step": "Step 3 - Target audit",
    }

    (MANIFEST_DIR / "batch_1_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md_lines = []
    md_lines.append("# Batch 1 Summary\n")
    md_lines.append("Batch scope:")
    md_lines.append("- Step 0: Verify raw files")
    md_lines.append("- Step 1: Raw schema audit")
    md_lines.append("- Step 2: Relationship audit\n")

    md_lines.append("## Progress\n")
    md_lines.append(f"- Completed technical steps: `{completed}/{total_technical_steps}`")
    md_lines.append(f"- Remaining technical steps: `{remaining}/{total_technical_steps}`")
    md_lines.append("- Next step: `Step 3 - Target audit`\n")

    md_lines.append("## Step Evaluation\n")
    md_lines.append("| Step | Name | Status |")
    md_lines.append("|---|---|---|")
    for s, n, st in step_statuses:
        md_lines.append(f"| {s} | {n} | `{st}` |")

    md_lines.append("\n## Produced Files\n")
    md_lines.append("- `data/manifests/raw_file_manifest.json`")
    md_lines.append("- `data/reports/raw_schema_audit_report.md`")
    md_lines.append("- `data/reports/raw_schema_summary.csv`")
    md_lines.append("- `data/reports/relationship_audit_report.md`")
    md_lines.append("- `data/manifests/batch_1_summary.json`")

    (REPORT_DIR / "batch_1_summary.md").write_text("\n".join(md_lines), encoding="utf-8")


def run_data_audit() -> None:
    create_directories(REPORT_DIR, MANIFEST_DIR)

    print("=== Batch 1: Raw verification + schema audit + relationship audit ===")

    print("\n[Step 0] Verify raw files")
    step0 = step_0_verify_raw_files()
    print(f"Step 0 status: {step0['status']}")

    if step0["status"] != "raw_verified":
        print("Blocked at Step 0. Fix missing/unreadable raw files first.")
        write_batch_summary(step0, {"status": "not_started"}, {"status": "not_started"})
        return

    print("\n[Step 1] Raw schema audit")
    step1 = step_1_raw_schema_audit()
    print(f"Step 1 status: {step1['status']}")

    if step1["status"] != "schema_audit_passed":
        print("Blocked at Step 1. Fix schema/key issues first.")
        write_batch_summary(step0, step1, {"status": "not_started"})
        return

    print("\n[Step 2] Relationship audit")
    step2 = step_2_relationship_audit()
    print(f"Step 2 status: {step2['status']}")

    write_batch_summary(step0, step1, step2)

    print("\n=== Batch 1 completed ===")
    print("Produced files:")
    print("- data/manifests/raw_file_manifest.json")
    print("- data/manifests/batch_1_summary.json")
    print("- data/reports/raw_schema_audit_report.md")
    print("- data/reports/raw_schema_summary.csv")
    print("- data/reports/relationship_audit_report.md")
    print("- data/reports/batch_1_summary.md")
