from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
REPORT_DIR = PROJECT_ROOT / "data" / "reports"
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"

REPORT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_FILES = [
    "application_train.csv",
    "bureau.csv",
    "bureau_balance.csv",
    "previous_application.csv",
    "installments_payments.csv",
    "POS_CASH_balance.csv",
    "credit_card_balance.csv",
]

DAY_COLUMN_KEYWORDS = [
    "DAYS_",
    "MONTHS_",
]

SPECIAL_ANOMALY_RULES = {
    "application_train.csv": {
        "AMT_INCOME_TOTAL": "<=0",
        "AMT_CREDIT": "<=0",
        "AMT_ANNUITY": "<=0",
        "AMT_GOODS_PRICE": "<=0",
        "DAYS_BIRTH": ">=0",
        "DAYS_EMPLOYED": "abnormal_days_employed",
        "CNT_FAM_MEMBERS": "<=0",
    },
    "installments_payments.csv": {
        "AMT_INSTALMENT": "<=0",
        "AMT_PAYMENT": "<0",
    },
    "credit_card_balance.csv": {
        "AMT_CREDIT_LIMIT_ACTUAL": "<=0",
        "AMT_INST_MIN_REGULARITY": "<=0",
        "AMT_PAYMENT_TOTAL_CURRENT": "<0",
        "AMT_DRAWINGS_CURRENT": "<0",
        "AMT_BALANCE": "<0",
    },
    "bureau.csv": {
        "AMT_CREDIT_SUM": "<=0",
        "AMT_CREDIT_SUM_DEBT": "<0",
        "AMT_CREDIT_SUM_LIMIT": "<0",
        "AMT_CREDIT_SUM_OVERDUE": "<0",
        "CREDIT_DAY_OVERDUE": "<0",
    },
    "previous_application.csv": {
        "AMT_APPLICATION": "<=0",
        "AMT_CREDIT": "<=0",
        "AMT_ANNUITY": "<=0",
        "AMT_GOODS_PRICE": "<=0",
    },
    "POS_CASH_balance.csv": {
        "SK_DPD": "<0",
        "SK_DPD_DEF": "<0",
        "CNT_INSTALMENT": "<0",
        "CNT_INSTALMENT_FUTURE": "<0",
    },
}


def read_csv_columns(filename: str) -> list[str]:
    path = RAW_DIR / filename
    return pd.read_csv(path, nrows=0).columns.tolist()


def is_numeric_dtype(dtype: str) -> bool:
    return any(x in dtype for x in ["int", "float"])


def apply_anomaly_rule(series: pd.Series, rule: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")

    if rule == "<=0":
        return numeric <= 0

    if rule == "<0":
        return numeric < 0

    if rule == ">=0":
        return numeric >= 0

    if rule == "abnormal_days_employed":
        # Home Credit thường có sentinel 365243 cho DAYS_EMPLOYED.
        return (numeric >= 0) | (numeric == 365243)

    return pd.Series(False, index=series.index)


def step_3_target_audit() -> dict:
    print("[Step 3] Target audit ...")

    path = RAW_DIR / "application_train.csv"

    if not path.exists():
        raise FileNotFoundError("application_train.csv not found in data/raw/")

    df = pd.read_csv(path, usecols=["SK_ID_CURR", "TARGET"])

    total_rows = len(df)
    target_missing = int(df["TARGET"].isna().sum())
    target_values = sorted(df["TARGET"].dropna().unique().tolist())

    target_counts = df["TARGET"].value_counts(dropna=False).to_dict()
    target_0_count = int((df["TARGET"] == 0).sum())
    target_1_count = int((df["TARGET"] == 1).sum())
    positive_rate = round(target_1_count / total_rows, 6) if total_rows else 0

    duplicate_customer_count = int(df["SK_ID_CURR"].duplicated().sum())
    target_per_customer = df.groupby("SK_ID_CURR")["TARGET"].nunique(dropna=False)
    duplicate_target_per_customer = int((target_per_customer > 1).sum())

    valid_target_values = set(target_values).issubset({0, 1})
    no_missing_target = target_missing == 0

    if positive_rate < 0.2:
        imbalance_assessment = "class_imbalance_expected_and_significant"
    else:
        imbalance_assessment = "class_imbalance_mild_or_moderate"

    recommended_metrics = [
        "ROC-AUC",
        "PR-AUC",
        "Recall",
        "Precision",
        "F1-score",
        "Confusion matrix",
        "Calibration if time allows",
    ]

    status = (
        "target_audit_passed"
        if valid_target_values and no_missing_target and duplicate_target_per_customer == 0
        else "blocked"
    )

    result = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "total_rows": total_rows,
        "target_values": target_values,
        "target_counts": {str(k): int(v) for k, v in target_counts.items()},
        "target_0_count": target_0_count,
        "target_1_count": target_1_count,
        "target_1_ratio": positive_rate,
        "target_missing": target_missing,
        "duplicate_sk_id_curr_count": duplicate_customer_count,
        "duplicate_target_per_customer": duplicate_target_per_customer,
        "class_imbalance_assessment": imbalance_assessment,
        "recommended_metrics": recommended_metrics,
        "split_recommendation": "Use stratified train/valid/test split by TARGET.",
        "status": status,
    }

    md = []
    md.append("# Target Audit Report\n")
    md.append(f"Created at: `{result['created_at']}`\n")
    md.append("## Target Summary\n")
    md.append(f"- Total rows: `{total_rows}`")
    md.append(f"- TARGET values found: `{target_values}`")
    md.append(f"- TARGET missing count: `{target_missing}`")
    md.append(f"- TARGET = 0 count: `{target_0_count}`")
    md.append(f"- TARGET = 1 count: `{target_1_count}`")
    md.append(f"- TARGET = 1 ratio: `{positive_rate}`")
    md.append(f"- Duplicate SK_ID_CURR count: `{duplicate_customer_count}`")
    md.append(f"- Duplicate target per SK_ID_CURR: `{duplicate_target_per_customer}`\n")

    md.append("## Class Imbalance Assessment\n")
    md.append(
        "This is a credit default risk problem, so class imbalance is expected. "
        "Model evaluation must not rely only on accuracy."
    )
    md.append(f"\nAssessment: `{imbalance_assessment}`\n")

    md.append("## Recommended Metrics for Model Stage\n")
    for metric in recommended_metrics:
        md.append(f"- {metric}")

    md.append("\n## Split Recommendation\n")
    md.append("- Use stratified train/validation/test split by `TARGET`.")
    md.append("- Split unit must be `SK_ID_CURR`.")
    md.append("- Preprocessing must be fitted only after the split, using training data only.\n")

    md.append("## Status\n")
    md.append(f"`{status}`\n")

    (REPORT_DIR / "target_audit_report.md").write_text("\n".join(md), encoding="utf-8")

    return result


def audit_missing_and_anomaly_for_file(filename: str, chunksize: int = 200_000) -> tuple[list[dict], list[dict]]:
    path = RAW_DIR / filename
    columns = read_csv_columns(filename)

    total_rows = 0
    missing_counts = defaultdict(int)
    non_null_counts = defaultdict(int)
    dtype_seen = defaultdict(set)
    infinite_counts = defaultdict(int)

    numeric_min = {}
    numeric_max = {}
    numeric_zero_count = defaultdict(int)
    numeric_negative_count = defaultdict(int)

    categorical_unique_values = defaultdict(set)
    rare_category_counts = defaultdict(lambda: defaultdict(int))

    special_rule_counts = defaultdict(int)

    day_columns = [
        col for col in columns
        if any(keyword in col for keyword in DAY_COLUMN_KEYWORDS)
    ]

    rules = SPECIAL_ANOMALY_RULES.get(filename, {})

    for chunk in pd.read_csv(path, chunksize=chunksize, low_memory=False):
        total_rows += len(chunk)

        for col in chunk.columns:
            s = chunk[col]
            dtype_seen[col].add(str(s.dtype))

            missing_counts[col] += int(s.isna().sum())
            non_null_counts[col] += int(s.notna().sum())

            if pd.api.types.is_numeric_dtype(s):
                numeric = pd.to_numeric(s, errors="coerce")

                if numeric.notna().any():
                    col_min = numeric.min(skipna=True)
                    col_max = numeric.max(skipna=True)

                    numeric_min[col] = col_min if col not in numeric_min else min(numeric_min[col], col_min)
                    numeric_max[col] = col_max if col not in numeric_max else max(numeric_max[col], col_max)

                numeric_zero_count[col] += int((numeric == 0).sum())
                numeric_negative_count[col] += int((numeric < 0).sum())

                inf_mask = numeric.isin([float("inf"), float("-inf")])
                infinite_counts[col] += int(inf_mask.sum())

            else:
                # Giới hạn để tránh ăn RAM với high-cardinality cực lớn.
                values = s.dropna().astype(str)
                if len(categorical_unique_values[col]) <= 20_000:
                    categorical_unique_values[col].update(values.unique().tolist())

                vc = values.value_counts()
                for category, count in vc.items():
                    if len(rare_category_counts[col]) <= 20_000:
                        rare_category_counts[col][category] += int(count)

            if col in rules:
                mask = apply_anomaly_rule(s, rules[col])
                special_rule_counts[col] += int(mask.sum())

    missing_rows = []
    anomaly_rows = []

    for col in columns:
        dtype_joined = "|".join(sorted(dtype_seen[col]))
        missing_count = int(missing_counts[col])
        missing_pct = round(missing_count / total_rows * 100, 4) if total_rows else 0

        unique_count = None
        high_cardinality = False
        rare_category_count = None

        if not any(is_numeric_dtype(dtype) for dtype in dtype_seen[col]):
            unique_count = len(categorical_unique_values[col])
            high_cardinality = unique_count > 50

            total_non_null = non_null_counts[col]
            rare_category_count = sum(
                1
                for _, count in rare_category_counts[col].items()
                if total_non_null > 0 and count / total_non_null < 0.01
            )

        missing_rows.append(
            {
                "table": filename,
                "column": col,
                "dtype_seen": dtype_joined,
                "row_count": total_rows,
                "missing_count": missing_count,
                "missing_percentage": missing_pct,
                "is_high_missing": missing_pct >= 40,
                "is_day_column": col in day_columns,
                "categorical_unique_count": unique_count,
                "is_high_cardinality_categorical": high_cardinality,
                "rare_category_count_below_1pct": rare_category_count,
            }
        )

        anomaly_rows.append(
            {
                "table": filename,
                "column": col,
                "dtype_seen": dtype_joined,
                "min_value": numeric_min.get(col),
                "max_value": numeric_max.get(col),
                "zero_count": int(numeric_zero_count[col]),
                "negative_count": int(numeric_negative_count[col]),
                "infinite_count": int(infinite_counts[col]),
                "special_rule": rules.get(col),
                "special_rule_violation_count": int(special_rule_counts[col]),
                "is_day_column": col in day_columns,
            }
        )

    return missing_rows, anomaly_rows


def step_4_missing_anomaly_audit() -> dict:
    print("[Step 4] Missing/anomaly audit ...")

    all_missing_rows = []
    all_anomaly_rows = []

    errors = []

    for filename in REQUIRED_FILES:
        print(f"[Step 4] Auditing {filename} ...")

        path = RAW_DIR / filename
        if not path.exists():
            errors.append(f"Missing file: {filename}")
            continue

        try:
            missing_rows, anomaly_rows = audit_missing_and_anomaly_for_file(filename)
            all_missing_rows.extend(missing_rows)
            all_anomaly_rows.extend(anomaly_rows)
        except Exception as e:
            errors.append(f"{filename}: {e}")

    missing_df = pd.DataFrame(all_missing_rows)
    anomaly_df = pd.DataFrame(all_anomaly_rows)

    missing_df.to_csv(REPORT_DIR / "missing_summary.csv", index=False)
    anomaly_df.to_csv(REPORT_DIR / "anomaly_summary.csv", index=False)

    high_missing = missing_df[missing_df["is_high_missing"] == True] if not missing_df.empty else pd.DataFrame()
    high_cardinality = (
        missing_df[missing_df["is_high_cardinality_categorical"] == True]
        if not missing_df.empty
        else pd.DataFrame()
    )
    special_violations = (
        anomaly_df[anomaly_df["special_rule_violation_count"] > 0]
        if not anomaly_df.empty
        else pd.DataFrame()
    )
    inf_violations = (
        anomaly_df[anomaly_df["infinite_count"] > 0]
        if not anomaly_df.empty
        else pd.DataFrame()
    )

    status = "missing_anomaly_audit_passed" if not errors else "warning_but_acceptable"

    result = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tables_audited": REQUIRED_FILES,
        "missing_summary_rows": int(len(missing_df)),
        "anomaly_summary_rows": int(len(anomaly_df)),
        "high_missing_column_count": int(len(high_missing)),
        "high_cardinality_categorical_count": int(len(high_cardinality)),
        "special_anomaly_violation_count": int(len(special_violations)),
        "infinite_value_column_count": int(len(inf_violations)),
        "status": status,
        "errors": errors,
    }

    md = []
    md.append("# Missing Value and Anomaly Audit Report\n")
    md.append(f"Created at: `{result['created_at']}`\n")

    md.append("## Summary\n")
    md.append(f"- Tables audited: `{len(REQUIRED_FILES)}`")
    md.append(f"- Columns profiled for missing values: `{len(missing_df)}`")
    md.append(f"- Columns profiled for anomalies: `{len(anomaly_df)}`")
    md.append(f"- High missing columns >= 40%: `{len(high_missing)}`")
    md.append(f"- High-cardinality categorical columns: `{len(high_cardinality)}`")
    md.append(f"- Columns with special anomaly violations: `{len(special_violations)}`")
    md.append(f"- Columns with infinite values: `{len(inf_violations)}`\n")

    md.append("## High Missing Columns\n")
    if high_missing.empty:
        md.append("No columns with missing percentage >= 40%.\n")
    else:
        md.append("| Table | Column | Missing % |")
        md.append("|---|---|---:|")
        for _, row in high_missing.sort_values("missing_percentage", ascending=False).head(50).iterrows():
            md.append(f"| {row['table']} | {row['column']} | {row['missing_percentage']} |")
        md.append("")

    md.append("## High-cardinality Categorical Columns\n")
    if high_cardinality.empty:
        md.append("No high-cardinality categorical columns detected using the current threshold.\n")
    else:
        md.append("| Table | Column | Unique count | Rare category count below 1% |")
        md.append("|---|---|---:|---:|")
        for _, row in high_cardinality.sort_values("categorical_unique_count", ascending=False).head(50).iterrows():
            md.append(
                f"| {row['table']} | {row['column']} | "
                f"{row['categorical_unique_count']} | {row['rare_category_count_below_1pct']} |"
            )
        md.append("")

    md.append("## Special Anomaly Violations\n")
    if special_violations.empty:
        md.append("No special anomaly violations detected.\n")
    else:
        md.append("| Table | Column | Rule | Violation count |")
        md.append("|---|---|---|---:|")
        for _, row in special_violations.sort_values("special_rule_violation_count", ascending=False).iterrows():
            md.append(
                f"| {row['table']} | {row['column']} | "
                f"{row['special_rule']} | {row['special_rule_violation_count']} |"
            )
        md.append("")

    md.append("## Infinite Value Check\n")
    if inf_violations.empty:
        md.append("No infinite values detected in raw numeric columns.\n")
    else:
        md.append("| Table | Column | Infinite count |")
        md.append("|---|---|---:|")
        for _, row in inf_violations.iterrows():
            md.append(f"| {row['table']} | {row['column']} | {row['infinite_count']} |")
        md.append("")

    md.append("## Important Notes for Next Stage\n")
    md.append("- Missing values are not imputed in this audit stage.")
    md.append("- Numeric values are not scaled or standardized in this audit stage.")
    md.append("- Ratio features must use safe division in the feature engineering stage.")
    md.append("- `DAYS_EMPLOYED` abnormal sentinel values must be handled before deriving `employment_years`.")
    md.append("- Any `inf` or `-inf` values produced later must be converted to `NaN` before preprocessing.")
    md.append("- Preprocessing must be fitted only after train/valid/test split.\n")

    if errors:
        md.append("## Errors / Warnings\n")
        for err in errors:
            md.append(f"- {err}")
        md.append("")

    md.append("## Status\n")
    md.append(f"`{status}`\n")

    (REPORT_DIR / "missing_anomaly_report.md").write_text("\n".join(md), encoding="utf-8")

    return result


def write_a2_summary(target_result: dict, missing_result: dict) -> None:
    previous_completed_steps = 3
    newly_completed = 0

    if target_result["status"] == "target_audit_passed":
        newly_completed += 1

    if missing_result["status"] in {"missing_anomaly_audit_passed", "warning_but_acceptable"}:
        newly_completed += 1

    completed = previous_completed_steps + newly_completed
    total = 20
    remaining = total - completed

    group_status = (
        "raw_audit_layer_completed"
        if newly_completed == 2
        else "raw_audit_layer_incomplete"
    )

    summary = {
        "batch_name": "batch_a2_target_missing_audit",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "assumption": "Step 0, Step 1, Step 2 were already completed.",
        "new_steps": [
            {
                "step": "Step 3",
                "name": "Target audit",
                "status": target_result["status"],
            },
            {
                "step": "Step 4",
                "name": "Missing/anomaly audit",
                "status": missing_result["status"],
            },
        ],
        "technical_steps_completed": completed,
        "technical_steps_total": total,
        "technical_steps_remaining": remaining,
        "pipeline_group": "Raw Audit Layer",
        "pipeline_group_status": group_status,
        "next_group": "Batch B - Feature Engineering Layer",
    }

    (MANIFEST_DIR / "batch_a2_target_missing_audit_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = []
    md.append("# Batch A2 Summary — Target + Missing/Anomaly Audit\n")
    md.append("Assumption: Step 0, Step 1, and Step 2 were already completed.\n")

    md.append("## Steps Completed in This Batch\n")
    md.append("| Step | Name | Status |")
    md.append("|---|---|---|")
    md.append(f"| Step 3 | Target audit | `{target_result['status']}` |")
    md.append(f"| Step 4 | Missing/anomaly audit | `{missing_result['status']}` |\n")

    md.append("## Overall Progress\n")
    md.append(f"- Technical steps completed: `{completed}/{total}`")
    md.append(f"- Technical steps remaining: `{remaining}/{total}`")
    md.append(f"- Pipeline group: `Raw Audit Layer`")
    md.append(f"- Pipeline group status: `{group_status}`")
    md.append("- Next group: `Batch B - Feature Engineering Layer`\n")

    md.append("## Produced Files\n")
    md.append("- `data/reports/target_audit_report.md`")
    md.append("- `data/reports/missing_anomaly_report.md`")
    md.append("- `data/reports/missing_summary.csv`")
    md.append("- `data/reports/anomaly_summary.csv`")
    md.append("- `data/reports/batch_a2_target_missing_audit_summary.md`")
    md.append("- `data/manifests/batch_a2_target_missing_audit_summary.json`\n")

    md.append("## Meaning for Next Stage\n")
    md.append(
        "The project can proceed to feature engineering only after the target distribution, "
        "missing patterns, anomaly risks, and ratio-denominator risks are understood. "
        "No preprocessing, scaling, one-hot encoding, or model training has been performed in this batch."
    )

    (REPORT_DIR / "batch_a2_target_missing_audit_summary.md").write_text(
        "\n".join(md),
        encoding="utf-8",
    )


def main() -> None:
    print("=== Batch A2: Target audit + Missing/anomaly audit ===")
    print("Assuming Step 0, Step 1, and Step 2 were already completed.\n")

    target_result = step_3_target_audit()
    print(f"Step 3 status: {target_result['status']}")

    missing_result = step_4_missing_anomaly_audit()
    print(f"Step 4 status: {missing_result['status']}")

    write_a2_summary(target_result, missing_result)

    print("\n=== Batch A2 completed ===")
    print("Produced files:")
    print("- data/reports/target_audit_report.md")
    print("- data/reports/missing_anomaly_report.md")
    print("- data/reports/missing_summary.csv")
    print("- data/reports/anomaly_summary.csv")
    print("- data/reports/batch_a2_target_missing_audit_summary.md")
    print("- data/manifests/batch_a2_target_missing_audit_summary.json")


if __name__ == "__main__":
    main()