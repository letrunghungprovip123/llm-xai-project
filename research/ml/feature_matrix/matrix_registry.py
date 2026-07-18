from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from ..common.dataframes import (
    count_infinite_values as count_inf,
    replace_infinite_with_nan as replace_inf_with_nan,
)
from ..common.paths import DEFAULT_PATHS


PROJECT_ROOT = DEFAULT_PATHS.project_root
RAW_DIR = DEFAULT_PATHS.raw_dir
INTERIM_DIR = DEFAULT_PATHS.interim_dir
PROCESSED_DIR = DEFAULT_PATHS.processed_dir
REPORT_DIR = DEFAULT_PATHS.report_dir
MANIFEST_DIR = DEFAULT_PATHS.manifest_dir
REGISTRY_DIR = DEFAULT_PATHS.registry_dir


FEATURE_GROUP_FILES = [
    {
        "name": "application_features",
        "path": INTERIM_DIR / "application_features.parquet",
        "concept_hint": "application_profile",
    },
    {
        "name": "bureau_features",
        "path": INTERIM_DIR / "bureau_features.parquet",
        "concept_hint": "external_credit_history",
    },
    {
        "name": "bureau_balance_features",
        "path": INTERIM_DIR / "bureau_balance_features.parquet",
        "concept_hint": "bureau_monthly_behavior",
    },
    {
        "name": "previous_application_features",
        "path": INTERIM_DIR / "previous_application_features.parquet",
        "concept_hint": "previous_application_behavior",
    },
    {
        "name": "installments_features",
        "path": INTERIM_DIR / "installments_features.parquet",
        "concept_hint": "installment_repayment_behavior",
    },
    {
        "name": "pos_cash_features",
        "path": INTERIM_DIR / "pos_cash_features.parquet",
        "concept_hint": "pos_cash_behavior",
    },
    {
        "name": "credit_card_features",
        "path": INTERIM_DIR / "credit_card_features.parquet",
        "concept_hint": "credit_card_usage_behavior",
    },
]

FORBIDDEN_IN_FEATURE_MATRIX = {
    "TARGET",
    "SK_ID_BUREAU",
    "SK_ID_PREV",
}

CONCEPT_REGISTRY: dict[str, dict[str, Any]] = {
    "application_profile": {
        "display_name": "hồ sơ khách hàng",
        "description": "Nhóm thông tin mô tả hồ sơ cơ bản của khách hàng.",
        "allowed_in_user_explanation": True,
        "sensitive_risk": "medium",
    },
    "applicant_stability": {
        "display_name": "độ ổn định hồ sơ",
        "description": "Nhóm yếu tố phản ánh độ ổn định nghề nghiệp, tuổi hồ sơ và thông tin đăng ký.",
        "allowed_in_user_explanation": True,
        "sensitive_risk": "medium",
    },
    "loan_affordability": {
        "display_name": "khả năng gánh khoản vay",
        "description": "Nhóm yếu tố phản ánh quan hệ giữa khoản vay, khoản trả định kỳ và thu nhập.",
        "allowed_in_user_explanation": True,
        "sensitive_risk": "low",
    },
    "external_score_signal": {
        "display_name": "tín hiệu điểm ngoài",
        "description": "Nhóm điểm/tín hiệu rủi ro bên ngoài có sẵn trong dữ liệu.",
        "allowed_in_user_explanation": "limited",
        "sensitive_risk": "medium",
    },
    "external_credit_history": {
        "display_name": "lịch sử tín dụng bên ngoài",
        "description": "Nhóm yếu tố phản ánh các khoản tín dụng của khách hàng tại tổ chức khác.",
        "allowed_in_user_explanation": True,
        "sensitive_risk": "low",
    },
    "bureau_monthly_behavior": {
        "display_name": "hành vi tín dụng hàng tháng từ bureau",
        "description": "Nhóm yếu tố phản ánh trạng thái hàng tháng của các khoản tín dụng bên ngoài.",
        "allowed_in_user_explanation": True,
        "sensitive_risk": "low",
    },
    "previous_application_behavior": {
        "display_name": "lịch sử đơn vay trước đó",
        "description": "Nhóm yếu tố phản ánh trạng thái các đơn vay trước đây của khách hàng.",
        "allowed_in_user_explanation": True,
        "sensitive_risk": "low",
    },
    "installment_repayment_behavior": {
        "display_name": "hành vi trả góp",
        "description": "Nhóm yếu tố phản ánh mức độ đúng hạn và đầy đủ trong các kỳ thanh toán trả góp.",
        "allowed_in_user_explanation": True,
        "sensitive_risk": "low",
    },
    "pos_cash_behavior": {
        "display_name": "hành vi khoản vay POS/CASH",
        "description": "Nhóm yếu tố phản ánh trạng thái và quá hạn của các khoản vay POS/CASH.",
        "allowed_in_user_explanation": True,
        "sensitive_risk": "low",
    },
    "credit_card_usage_behavior": {
        "display_name": "hành vi sử dụng thẻ tín dụng",
        "description": "Nhóm yếu tố phản ánh dư nợ, hạn mức, thanh toán tối thiểu và quá hạn trên thẻ tín dụng.",
        "allowed_in_user_explanation": True,
        "sensitive_risk": "low",
    },
    "unknown_feature_group": {
        "display_name": "nhóm feature chưa phân loại",
        "description": "Nhóm fallback cho các feature chưa map được concept rõ ràng.",
        "allowed_in_user_explanation": False,
        "sensitive_risk": "unknown",
    },
}


def relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_inputs_exist() -> None:
    missing = []

    train_path = RAW_DIR / "application_train.csv"
    if not train_path.exists():
        missing.append(relative(train_path))

    for group in FEATURE_GROUP_FILES:
        if not group["path"].exists():
            missing.append(relative(group["path"]))

    if missing:
        raise FileNotFoundError(f"Missing required input files: {missing}")


def load_target() -> pd.DataFrame:
    print("[Batch C] Loading target from application_train.csv ...")

    target = pd.read_csv(
        RAW_DIR / "application_train.csv",
        usecols=["SK_ID_CURR", "TARGET"],
    )

    if "SK_ID_CURR" not in target.columns:
        raise ValueError("application_train.csv is missing SK_ID_CURR")

    if "TARGET" not in target.columns:
        raise ValueError("application_train.csv is missing TARGET")

    duplicate_ids = int(target["SK_ID_CURR"].duplicated().sum())
    if duplicate_ids > 0:
        raise ValueError(f"application_train.csv has duplicate SK_ID_CURR: {duplicate_ids}")

    missing_target = int(target["TARGET"].isna().sum())
    if missing_target > 0:
        raise ValueError(f"TARGET has missing values: {missing_target}")

    return target


def validate_target(target: pd.DataFrame) -> dict[str, Any]:
    errors = []

    row_count = len(target)
    duplicate_ids = int(target["SK_ID_CURR"].duplicated().sum())
    missing_target = int(target["TARGET"].isna().sum())
    target_values = sorted(target["TARGET"].dropna().unique().tolist())

    if duplicate_ids > 0:
        errors.append(f"duplicate SK_ID_CURR: {duplicate_ids}")

    if missing_target > 0:
        errors.append(f"missing TARGET: {missing_target}")

    if not set(target_values).issubset({0, 1}):
        errors.append(f"unexpected TARGET values: {target_values}")

    return {
        "row_count": int(row_count),
        "column_count": int(len(target.columns)),
        "duplicate_sk_id_curr": duplicate_ids,
        "missing_target": missing_target,
        "target_values": target_values,
        "target_positive_count": int((target["TARGET"] == 1).sum()),
        "target_negative_count": int((target["TARGET"] == 0).sum()),
        "target_positive_rate": float((target["TARGET"] == 1).mean()),
        "status": "passed" if not errors else "blocked",
        "errors": errors,
    }


def validate_feature_group_before_merge(df: pd.DataFrame, group_name: str) -> dict[str, Any]:
    errors = []

    if "SK_ID_CURR" not in df.columns:
        errors.append("missing SK_ID_CURR")
        duplicate_ids = None
    else:
        duplicate_ids = int(df["SK_ID_CURR"].duplicated().sum())
        if duplicate_ids > 0:
            errors.append(f"duplicate SK_ID_CURR: {duplicate_ids}")

    forbidden_found = sorted([c for c in FORBIDDEN_IN_FEATURE_MATRIX if c in df.columns])
    if forbidden_found:
        errors.append(f"forbidden columns found: {forbidden_found}")

    inf_count = count_inf(df)
    if inf_count > 0:
        errors.append(f"inf/-inf values found: {inf_count}")

    feature_columns = [c for c in df.columns if c != "SK_ID_CURR"]

    all_null_features = [
        c for c in feature_columns
        if df[c].isna().all()
    ]

    constant_features = [
        c for c in feature_columns
        if df[c].nunique(dropna=False) <= 1
    ]

    return {
        "group_name": group_name,
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "feature_count": int(len(feature_columns)),
        "duplicate_sk_id_curr": duplicate_ids,
        "forbidden_columns_found": forbidden_found,
        "inf_count": inf_count,
        "all_null_feature_count": len(all_null_features),
        "all_null_features": all_null_features[:50],
        "constant_feature_count": len(constant_features),
        "constant_features": constant_features[:50],
        "status": "passed" if not errors else "blocked",
        "errors": errors,
    }


def build_unified_feature_matrix() -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    target = load_target()

    expected_rows = len(target)
    print(f"[Batch C] Base rows: {expected_rows}")

    matrix = target[["SK_ID_CURR"]].copy()
    used_columns = set(matrix.columns)
    group_stats: list[dict[str, Any]] = []

    for group in FEATURE_GROUP_FILES:
        group_name = group["name"]
        path = group["path"]

        print(f"[Batch C] Reading {relative(path)} ...")

        df = pd.read_parquet(path)
        df = replace_inf_with_nan(df)

        stats = validate_feature_group_before_merge(df, group_name)

        if stats["status"] != "passed":
            group_stats.append(stats)
            raise ValueError(
                f"Feature group validation failed: {group_name}: {stats['errors']}"
            )

        feature_columns = [c for c in df.columns if c != "SK_ID_CURR"]
        overlapping = sorted([c for c in feature_columns if c in used_columns])

        if overlapping:
            raise ValueError(
                f"Column name collision before merging {group_name}: {overlapping[:50]}"
            )

        before_rows = len(matrix)
        matrix = matrix.merge(df, on="SK_ID_CURR", how="left")
        after_rows = len(matrix)

        if after_rows != before_rows:
            raise ValueError(
                f"Row count changed after merging {group_name}: before={before_rows}, after={after_rows}"
            )

        duplicate_after_merge = int(matrix["SK_ID_CURR"].duplicated().sum())
        if duplicate_after_merge > 0:
            raise ValueError(
                f"Duplicate SK_ID_CURR appeared after merging {group_name}: {duplicate_after_merge}"
            )

        used_columns.update(feature_columns)

        stats["status"] = "merged"
        group_stats.append(stats)

        print(
            f"[Batch C] Merged {group_name}: "
            f"rows={after_rows}, added_features={len(feature_columns)}"
        )

    target = target[["SK_ID_CURR", "TARGET"]].copy()

    return matrix, target, group_stats


def infer_concept(feature_name: str) -> str:
    application_profile_features = {
        "CNT_CHILDREN",
        "CNT_FAM_MEMBERS",
        "AMT_INCOME_TOTAL",
        "AMT_CREDIT",
        "AMT_ANNUITY",
        "AMT_GOODS_PRICE",
        "NAME_CONTRACT_TYPE",
        "NAME_INCOME_TYPE",
        "NAME_EDUCATION_TYPE",
        "NAME_FAMILY_STATUS",
        "NAME_HOUSING_TYPE",
        "OCCUPATION_TYPE",
        "ORGANIZATION_TYPE",
    }

    applicant_stability_features = {
        "age_years",
        "employment_years",
        "registration_years",
        "id_publish_years",
        "days_employed_abnormal",
    }

    loan_affordability_features = {
        "credit_to_income_ratio",
        "annuity_to_income_ratio",
        "goods_price_to_income_ratio",
        "annuity_to_credit_ratio",
        "credit_to_goods_price_ratio",
        "income_per_family_member",
    }

    if feature_name in application_profile_features:
        return "application_profile"

    if feature_name in applicant_stability_features:
        return "applicant_stability"

    if feature_name in loan_affordability_features:
        return "loan_affordability"

    if feature_name.startswith("EXT_SOURCE_") or feature_name.startswith("ext_source_"):
        return "external_score_signal"

    if feature_name.startswith("bureau_balance_") or feature_name == "has_bureau_balance_history":
        return "bureau_monthly_behavior"

    if feature_name.startswith("bureau_") or feature_name == "has_bureau_history":
        return "external_credit_history"

    if feature_name.startswith("previous_") or feature_name == "has_previous_application_history":
        return "previous_application_behavior"

    if feature_name.startswith("installment_") or feature_name == "has_installment_history":
        return "installment_repayment_behavior"

    if feature_name.startswith("pos_cash_") or feature_name == "has_pos_cash_history":
        return "pos_cash_behavior"

    if feature_name.startswith("credit_card_") or feature_name == "has_credit_card_history":
        return "credit_card_usage_behavior"

    return "unknown_feature_group"


def infer_source_table(feature_name: str) -> str:
    if feature_name.startswith("bureau_balance_") or feature_name == "has_bureau_balance_history":
        return "bureau_balance"

    if feature_name.startswith("bureau_") or feature_name == "has_bureau_history":
        return "bureau"

    if feature_name.startswith("previous_") or feature_name == "has_previous_application_history":
        return "previous_application"

    if feature_name.startswith("installment_") or feature_name == "has_installment_history":
        return "installments_payments"

    if feature_name.startswith("pos_cash_") or feature_name == "has_pos_cash_history":
        return "POS_CASH_balance"

    if feature_name.startswith("credit_card_") or feature_name == "has_credit_card_history":
        return "credit_card_balance"

    return "application_train"


def infer_feature_group_file(feature_name: str) -> str:
    source_table = infer_source_table(feature_name)

    mapping = {
        "application_train": "application_features.parquet",
        "bureau": "bureau_features.parquet",
        "bureau_balance": "bureau_balance_features.parquet",
        "previous_application": "previous_application_features.parquet",
        "installments_payments": "installments_features.parquet",
        "POS_CASH_balance": "pos_cash_features.parquet",
        "credit_card_balance": "credit_card_features.parquet",
    }

    return mapping.get(source_table, "unknown")


def infer_value_type(feature_name: str, dtype: Any) -> str:
    lower = feature_name.lower()

    manual_value_types = {
        "CNT_CHILDREN": "count",
        "CNT_FAM_MEMBERS": "count",
        "AMT_INCOME_TOTAL": "amount",
        "AMT_CREDIT": "amount",
        "AMT_ANNUITY": "amount",
        "AMT_GOODS_PRICE": "amount",
        "NAME_CONTRACT_TYPE": "categorical",
        "NAME_INCOME_TYPE": "categorical",
        "NAME_EDUCATION_TYPE": "categorical",
        "NAME_FAMILY_STATUS": "categorical",
        "NAME_HOUSING_TYPE": "categorical",
        "OCCUPATION_TYPE": "categorical",
        "ORGANIZATION_TYPE": "categorical",

        "age_years": "years",
        "employment_years": "years",
        "registration_years": "years",
        "id_publish_years": "years",
        "days_employed_abnormal": "binary_indicator",

        "EXT_SOURCE_1": "score",
        "EXT_SOURCE_2": "score",
        "EXT_SOURCE_3": "score",
        "ext_source_mean": "score",
        "ext_source_min": "score",
        "ext_source_max": "score",
        "ext_source_std": "score",
        "ext_source_missing_count": "count",

        "credit_to_income_ratio": "ratio",
        "annuity_to_income_ratio": "ratio",
        "goods_price_to_income_ratio": "ratio",
        "annuity_to_credit_ratio": "ratio",
        "credit_to_goods_price_ratio": "ratio",
        "income_per_family_member": "amount",

        "bureau_total_loans": "count",
        "bureau_record_count": "count",
        "bureau_active_loan_count": "count",
        "bureau_closed_loan_count": "count",
        "bureau_sold_loan_count": "count",
        "bureau_bad_debt_count": "count",
        "bureau_overdue_count": "count",
        "bureau_recent_loan_count": "count",
        "bureau_max_days_credit_overdue": "days",
        "bureau_avg_days_credit_overdue": "days",
        "bureau_avg_days_credit": "days",
        "bureau_min_days_credit": "days",
        "bureau_max_days_credit": "days",
        "bureau_long_history_months": "months",
        "bureau_debt_to_credit_ratio": "ratio",

        "bureau_balance_months_observed": "count",
        "bureau_balance_good_status_count": "count",
        "bureau_balance_bad_status_count": "count",
        "bureau_balance_closed_status_count": "count",
        "bureau_balance_unknown_status_count": "count",
        "bureau_balance_recent_month_count": "count",
        "bureau_balance_recent_bad_status_count": "count",
        "bureau_balance_max_status_numeric": "numeric",
        "bureau_balance_avg_status_numeric": "numeric",
        "bureau_balance_bad_status_ratio": "ratio",
        "bureau_balance_recent_bad_status_ratio": "ratio",

        "previous_application_count": "count",
        "previous_approved_count": "count",
        "previous_refused_count": "count",
        "previous_canceled_count": "count",
        "previous_unused_offer_count": "count",
        "previous_recent_application_count": "count",
        "previous_cash_loan_count": "count",
        "previous_consumer_loan_count": "count",
        "previous_revolving_loan_count": "count",
        "previous_avg_days_decision": "days",
        "previous_approval_ratio": "ratio",
        "previous_refusal_ratio": "ratio",
        "previous_canceled_ratio": "ratio",
        "previous_credit_to_application_ratio": "ratio",

        "installment_count": "count",
        "installment_late_payment_count": "count",
        "installment_early_payment_count": "count",
        "installment_underpayment_count": "count",
        "installment_fully_paid_count": "count",
        "installment_recent_count": "count",
        "installment_recent_late_payment_count": "count",
        "installment_recent_underpayment_count": "count",
        "installment_avg_days_late": "days",
        "installment_max_days_late": "days",
        "installment_sum_days_late": "days",
        "installment_avg_days_early": "days",
        "installment_max_days_early": "days",
        "installment_late_payment_ratio": "ratio",
        "installment_early_payment_ratio": "ratio",
        "installment_underpayment_ratio": "ratio",
        "installment_recent_late_payment_ratio": "ratio",
        "installment_recent_underpayment_ratio": "ratio",
        "installment_payment_ratio_avg": "ratio",
        "installment_payment_ratio_min": "ratio",
        "installment_payment_ratio_max": "ratio",
        "installment_payment_ratio_std": "ratio",
        "installment_recent_payment_ratio_avg": "ratio",
        "installment_total_payment_gap": "amount",
        "installment_total_expected_amount": "amount",
        "installment_total_paid_amount": "amount",

        "pos_cash_months_observed": "count",
        "pos_cash_contract_count": "count",
        "pos_cash_avg_installment_count": "numeric",
        "pos_cash_avg_future_installment_count": "numeric",
        "pos_cash_min_future_installment_count": "numeric",
        "pos_cash_max_future_installment_count": "numeric",
        "pos_cash_dpd_count": "count",
        "pos_cash_def_dpd_count": "count",
        "pos_cash_active_count": "count",
        "pos_cash_completed_count": "count",
        "pos_cash_demand_count": "count",
        "pos_cash_signed_count": "count",
        "pos_cash_status_xna_count": "count",
        "pos_cash_avg_dpd": "days",
        "pos_cash_max_dpd": "days",
        "pos_cash_avg_def_dpd": "days",
        "pos_cash_max_def_dpd": "days",
        "pos_cash_dpd_ratio": "ratio",
        "pos_cash_def_dpd_ratio": "ratio",

        "credit_card_months_observed": "count",
        "credit_card_dpd_count": "count",
        "credit_card_def_dpd_count": "count",
        "credit_card_active_count": "count",
        "credit_card_completed_count": "count",
        "credit_card_signed_count": "count",
        "credit_card_avg_dpd": "days",
        "credit_card_max_dpd": "days",
        "credit_card_avg_def_dpd": "days",
        "credit_card_max_def_dpd": "days",
        "credit_card_avg_utilization": "ratio",
        "credit_card_max_utilization": "ratio",
        "credit_card_avg_payment_to_min_ratio": "ratio",
        "credit_card_min_payment_to_min_ratio": "ratio",
        "credit_card_avg_drawing_to_limit_ratio": "ratio",
        "credit_card_max_drawing_to_limit_ratio": "ratio",
        "credit_card_dpd_ratio": "ratio",
        "credit_card_def_dpd_ratio": "ratio",
    }

    if feature_name in manual_value_types:
        return manual_value_types[feature_name]

    if not pd.api.types.is_numeric_dtype(dtype):
        return "categorical"

    if lower.startswith("has_") or lower.endswith("_flag") or lower.endswith("_abnormal"):
        return "binary_indicator"

    if (
        lower.endswith("_ratio")
        or lower.endswith("_rate")
        or "_to_" in lower
        or "utilization" in lower
    ):
        return "ratio"

    if (
        lower.endswith("_count")
        or lower.endswith("_counts")
        or lower.endswith("_n")
        or "number_of" in lower
        or "months_observed" in lower
        or "record_count" in lower
        or "total_loans" in lower
    ):
        return "count"

    if "years" in lower:
        return "years"

    if "months" in lower or "month" in lower:
        return "months"

    if "days" in lower or "dpd" in lower:
        return "days"

    if "overdue" in lower and "amount" not in lower:
        return "days"

    if "ext_source" in lower:
        return "score"

    amount_keywords = [
        "amt_",
        "amount",
        "income",
        "annuity",
        "balance",
        "drawings",
        "payment_gap",
        "credit_sum",
        "credit_debt",
        "credit_limit",
        "total_paid",
        "total_expected",
        "overdue_amount",
        "avg_limit",
        "max_limit",
        "avg_balance",
        "max_balance",
        "min_balance",
        "avg_drawings",
        "max_drawings",
        "total_drawings",
    ]

    if any(keyword in lower for keyword in amount_keywords):
        return "amount"

    return "numeric"


def infer_unit(value_type: str) -> str | None:
    mapping = {
        "ratio": "ratio",
        "amount": "currency",
        "days": "days",
        "months": "months",
        "years": "years",
        "score": "score",
        "count": "count",
        "binary_indicator": "0_or_1",
        "categorical": None,
        "numeric": None,
    }

    return mapping.get(value_type)


def infer_formatting_rule(value_type: str) -> str:
    mapping = {
        "ratio": "ratio_as_percentage_1_decimal",
        "amount": "currency_rounded",
        "years": "number_1_decimal",
        "months": "integer",
        "days": "integer",
        "score": "number_3_decimal",
        "count": "integer",
        "binary_indicator": "boolean_indicator",
        "categorical": "category",
        "numeric": "number_3_decimal",
    }

    return mapping.get(value_type, "number_3_decimal")


def infer_data_kind(feature_name: str, dtype: Any) -> str:
    lower = feature_name.lower()

    if lower.startswith("has_") or lower.endswith("_flag") or lower.endswith("_abnormal"):
        return "binary"

    if not pd.api.types.is_numeric_dtype(dtype):
        return "categorical"

    return "numeric"


def infer_direction_prior(feature_name: str) -> str:
    lower = feature_name.lower()

    manual_direction = {
        "EXT_SOURCE_1": "higher_value_may_decrease_risk",
        "EXT_SOURCE_2": "higher_value_may_decrease_risk",
        "EXT_SOURCE_3": "higher_value_may_decrease_risk",
        "ext_source_mean": "higher_value_may_decrease_risk",
        "ext_source_min": "higher_value_may_decrease_risk",
        "ext_source_max": "higher_value_may_decrease_risk",

        "credit_to_income_ratio": "higher_value_may_increase_risk",
        "annuity_to_income_ratio": "higher_value_may_increase_risk",
        "bureau_debt_to_credit_ratio": "higher_value_may_increase_risk",
        "previous_refusal_ratio": "higher_value_may_increase_risk",
        "previous_refused_count": "higher_value_may_increase_risk",
        "installment_late_payment_ratio": "higher_value_may_increase_risk",
        "installment_late_payment_count": "higher_value_may_increase_risk",
        "installment_underpayment_ratio": "higher_value_may_increase_risk",
        "installment_underpayment_count": "higher_value_may_increase_risk",
        "installment_total_payment_gap": "higher_value_may_increase_risk",
        "pos_cash_dpd_ratio": "higher_value_may_increase_risk",
        "pos_cash_def_dpd_ratio": "higher_value_may_increase_risk",
        "credit_card_avg_utilization": "higher_value_may_increase_risk",
        "credit_card_max_utilization": "higher_value_may_increase_risk",
        "credit_card_dpd_ratio": "higher_value_may_increase_risk",
        "credit_card_def_dpd_ratio": "higher_value_may_increase_risk",

        "previous_approval_ratio": "higher_value_may_decrease_risk",
        "previous_approved_count": "higher_value_may_decrease_risk",
        "installment_early_payment_ratio": "higher_value_may_decrease_risk",
        "installment_fully_paid_count": "higher_value_may_decrease_risk",
        "bureau_closed_loan_count": "higher_value_may_decrease_risk",
        "bureau_balance_good_status_count": "higher_value_may_decrease_risk",
    }

    if feature_name in manual_direction:
        return manual_direction[feature_name]

    higher_risk_keywords = [
        "late",
        "underpayment",
        "overdue",
        "bad_debt",
        "bad_status",
        "dpd",
        "debt_to_credit",
        "credit_to_income",
        "annuity_to_income",
        "payment_gap",
        "refusal",
        "refused",
        "canceled",
        "utilization",
        "max_days_late",
    ]

    lower_risk_keywords = [
        "approved",
        "approval",
        "early",
        "fully_paid",
        "closed",
        "good_status",
        "ext_source",
    ]

    if any(keyword in lower for keyword in higher_risk_keywords):
        return "higher_value_may_increase_risk"

    if any(keyword in lower for keyword in lower_risk_keywords):
        return "higher_value_may_decrease_risk"

    return "unknown"


def infer_sensitive_flag(feature_name: str, concept: str) -> bool:
    sensitive_features = {
        "NAME_EDUCATION_TYPE",
        "NAME_FAMILY_STATUS",
        "OCCUPATION_TYPE",
        "ORGANIZATION_TYPE",
        "age_years",
        "CNT_CHILDREN",
        "CNT_FAM_MEMBERS",
    }

    if feature_name in sensitive_features:
        return True

    if concept == "external_score_signal":
        return True

    return False


def infer_allowed_in_user_explanation(feature_name: str, concept: str) -> bool | str:
    if concept == "unknown_feature_group":
        return False

    if concept == "external_score_signal":
        return "limited"

    limited_profile_features = {
        "NAME_EDUCATION_TYPE",
        "NAME_FAMILY_STATUS",
        "OCCUPATION_TYPE",
        "ORGANIZATION_TYPE",
        "age_years",
        "CNT_CHILDREN",
        "CNT_FAM_MEMBERS",
    }

    if feature_name in limited_profile_features:
        return "limited"

    return True


def make_display_name(feature_name: str) -> str:
    manual = {
        "CNT_CHILDREN": "số con",
        "CNT_FAM_MEMBERS": "số thành viên gia đình",
        "AMT_INCOME_TOTAL": "tổng thu nhập",
        "AMT_CREDIT": "số tiền khoản vay hiện tại",
        "AMT_ANNUITY": "số tiền trả định kỳ",
        "AMT_GOODS_PRICE": "giá trị hàng hóa/khoản mua",
        "NAME_CONTRACT_TYPE": "loại hợp đồng vay",
        "NAME_INCOME_TYPE": "loại thu nhập",
        "NAME_EDUCATION_TYPE": "trình độ học vấn",
        "NAME_FAMILY_STATUS": "tình trạng gia đình",
        "NAME_HOUSING_TYPE": "loại nhà ở",
        "OCCUPATION_TYPE": "nghề nghiệp",
        "ORGANIZATION_TYPE": "loại tổ chức làm việc",
        "age_years": "tuổi của khách hàng",
        "employment_years": "số năm làm việc",
        "registration_years": "số năm từ khi đăng ký",
        "id_publish_years": "số năm từ khi cấp giấy tờ",
        "days_employed_abnormal": "dấu hiệu ngày làm việc bất thường",
        "credit_to_income_ratio": "tỷ lệ khoản vay trên thu nhập",
        "annuity_to_income_ratio": "tỷ lệ trả góp định kỳ trên thu nhập",
        "goods_price_to_income_ratio": "tỷ lệ giá trị hàng hóa trên thu nhập",
        "annuity_to_credit_ratio": "tỷ lệ trả góp định kỳ trên khoản vay",
        "credit_to_goods_price_ratio": "tỷ lệ khoản vay trên giá trị hàng hóa",
        "income_per_family_member": "thu nhập trên mỗi thành viên gia đình",
        "EXT_SOURCE_1": "tín hiệu điểm ngoài 1",
        "EXT_SOURCE_2": "tín hiệu điểm ngoài 2",
        "EXT_SOURCE_3": "tín hiệu điểm ngoài 3",
        "ext_source_mean": "trung bình tín hiệu điểm ngoài",
        "ext_source_min": "tín hiệu điểm ngoài thấp nhất",
        "ext_source_max": "tín hiệu điểm ngoài cao nhất",
        "ext_source_std": "độ biến động tín hiệu điểm ngoài",
        "ext_source_missing_count": "số lượng tín hiệu điểm ngoài bị thiếu",
        "bureau_record_count": "số bản ghi bureau",
        "bureau_total_loans": "tổng số khoản tín dụng bureau",
        "bureau_active_loan_count": "số khoản tín dụng bureau đang hoạt động",
        "bureau_closed_loan_count": "số khoản tín dụng bureau đã đóng",
        "bureau_sold_loan_count": "số khoản tín dụng bureau đã bán",
        "bureau_bad_debt_count": "số khoản nợ xấu bureau",
        "bureau_overdue_count": "số khoản bureau bị quá hạn",
        "bureau_max_days_credit_overdue": "số ngày quá hạn bureau lớn nhất",
        "bureau_avg_days_credit_overdue": "số ngày quá hạn bureau trung bình",
        "bureau_credit_sum_total": "tổng giá trị tín dụng bureau",
        "bureau_credit_debt_total": "tổng dư nợ bureau",
        "bureau_credit_limit_total": "tổng hạn mức tín dụng bureau",
        "bureau_overdue_amount_total": "tổng số tiền quá hạn bureau",
        "bureau_debt_to_credit_ratio": "tỷ lệ dư nợ trên tổng tín dụng bureau",
        "bureau_long_history_months": "độ dài lịch sử bureau theo tháng",
        "bureau_balance_months_observed": "số tháng bureau balance quan sát được",
        "bureau_balance_good_status_count": "số tháng bureau có trạng thái tốt",
        "bureau_balance_bad_status_count": "số tháng bureau có trạng thái xấu",
        "bureau_balance_bad_status_ratio": "tỷ lệ tháng bureau có trạng thái xấu",
        "previous_application_count": "số đơn vay trước đó",
        "previous_approved_count": "số đơn vay trước được duyệt",
        "previous_refused_count": "số đơn vay trước bị từ chối",
        "previous_approval_ratio": "tỷ lệ đơn vay trước được duyệt",
        "previous_refusal_ratio": "tỷ lệ đơn vay trước bị từ chối",
        "installment_late_payment_ratio": "tỷ lệ kỳ thanh toán bị trễ",
        "installment_underpayment_ratio": "tỷ lệ kỳ thanh toán trả thiếu",
        "installment_total_payment_gap": "tổng chênh lệch giữa số phải trả và đã trả",
        "credit_card_avg_utilization": "mức sử dụng thẻ tín dụng trung bình",
        "credit_card_max_utilization": "mức sử dụng thẻ tín dụng cao nhất",
        "credit_card_dpd_ratio": "tỷ lệ tháng thẻ tín dụng bị quá hạn",
        "pos_cash_dpd_ratio": "tỷ lệ tháng POS/CASH bị quá hạn",
        "has_bureau_history": "có lịch sử bureau hay không",
        "has_bureau_balance_history": "có lịch sử bureau balance hay không",
        "has_previous_application_history": "có lịch sử đơn vay trước hay không",
        "has_installment_history": "có lịch sử trả góp hay không",
        "has_pos_cash_history": "có lịch sử POS/CASH hay không",
        "has_credit_card_history": "có lịch sử thẻ tín dụng hay không",
    }

    if feature_name in manual:
        return manual[feature_name]

    return feature_name.replace("_", " ")


def make_description(feature_name: str, concept: str, source_table: str) -> str:
    concept_display = CONCEPT_REGISTRY[concept]["display_name"]
    return (
        f"Feature `{feature_name}` thuộc nhóm `{concept_display}`, "
        f"được tạo từ bảng `{source_table}` trong Data Layer."
    )


def build_feature_registry(matrix: pd.DataFrame) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}

    feature_columns = [
        c for c in matrix.columns
        if c != "SK_ID_CURR"
    ]

    for feature_name in feature_columns:
        concept = infer_concept(feature_name)
        source_table = infer_source_table(feature_name)
        source_feature_file = infer_feature_group_file(feature_name)
        value_type = infer_value_type(feature_name, matrix[feature_name].dtype)
        unit = infer_unit(value_type)
        data_kind = infer_data_kind(feature_name, matrix[feature_name].dtype)
        concept_meta = CONCEPT_REGISTRY[concept]

        allowed_in_user_explanation = infer_allowed_in_user_explanation(
            feature_name=feature_name,
            concept=concept,
        )

        sensitive = infer_sensitive_flag(
            feature_name=feature_name,
            concept=concept,
        )

        missing_rate = float(matrix[feature_name].isna().mean())
        non_null_count = int(matrix[feature_name].notna().sum())
        unique_count = int(matrix[feature_name].nunique(dropna=True))

        registry[feature_name] = {
            "feature_name": feature_name,
            "display_name": make_display_name(feature_name),
            "description": make_description(feature_name, concept, source_table),
            "concept": concept,
            "concept_display_name": concept_meta["display_name"],
            "source_table": source_table,
            "source_feature_file": source_feature_file,
            "data_kind": data_kind,
            "pandas_dtype": str(matrix[feature_name].dtype),
            "value_type": value_type,
            "unit": unit,
            "missing_rate": missing_rate,
            "non_null_count": non_null_count,
            "unique_count": unique_count,
            "sensitive": sensitive,
            "mutable": False,
            "allowed_for_model": True,
            "allowed_in_user_explanation": allowed_in_user_explanation,
            "allowed_in_recommendation": False,
            "direction_prior": infer_direction_prior(feature_name),
            "formatting_rule": infer_formatting_rule(value_type),
        }

    return registry


def registry_to_dataframe(feature_registry: dict[str, dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(list(feature_registry.values()))


def validate_feature_registry(
    matrix: pd.DataFrame,
    concept_registry: dict[str, dict[str, Any]],
    feature_registry: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    feature_columns = [
        c for c in matrix.columns
        if c != "SK_ID_CURR"
    ]

    missing_feature_registry = [
        c for c in feature_columns
        if c not in feature_registry
    ]

    extra_feature_registry = [
        c for c in feature_registry.keys()
        if c not in feature_columns
    ]

    concepts_used = sorted(set(meta["concept"] for meta in feature_registry.values()))

    missing_concepts = [
        c for c in concepts_used
        if c not in concept_registry
    ]

    features_missing_concept = [
        f for f, meta in feature_registry.items()
        if not meta.get("concept")
    ]

    explanation_blocked_features = [
        f for f, meta in feature_registry.items()
        if meta.get("allowed_in_user_explanation") is False
    ]

    explanation_limited_features = [
        f for f, meta in feature_registry.items()
        if meta.get("allowed_in_user_explanation") == "limited"
    ]

    sensitive_features = [
        f for f, meta in feature_registry.items()
        if meta.get("sensitive") is True
    ]

    suspicious_metadata = []

    for feature_name, meta in feature_registry.items():
        value_type = meta.get("value_type")
        data_kind = meta.get("data_kind")
        unit = meta.get("unit")

        if data_kind == "categorical" and value_type != "categorical":
            suspicious_metadata.append(
                f"{feature_name}: categorical data_kind but value_type={value_type}"
            )

        if value_type == "categorical" and unit is not None:
            suspicious_metadata.append(
                f"{feature_name}: categorical feature should not have unit={unit}"
            )

        if value_type == "days" and unit != "days":
            suspicious_metadata.append(
                f"{feature_name}: days feature should have unit=days"
            )

        if value_type == "years" and unit != "years":
            suspicious_metadata.append(
                f"{feature_name}: years feature should have unit=years"
            )

        if value_type == "amount" and unit != "currency":
            suspicious_metadata.append(
                f"{feature_name}: amount feature should have unit=currency"
            )

    errors = []

    if missing_feature_registry:
        errors.append(f"missing feature registry entries: {len(missing_feature_registry)}")

    if extra_feature_registry:
        errors.append(f"extra feature registry entries: {len(extra_feature_registry)}")

    if missing_concepts:
        errors.append(f"missing concepts: {missing_concepts}")

    if features_missing_concept:
        errors.append(f"features missing concept: {len(features_missing_concept)}")

    if suspicious_metadata:
        errors.append(f"suspicious metadata entries: {len(suspicious_metadata)}")

    return {
        "feature_count": len(feature_columns),
        "feature_registry_entry_count": len(feature_registry),
        "missing_feature_registry_count": len(missing_feature_registry),
        "missing_feature_registry": missing_feature_registry[:50],
        "extra_feature_registry_count": len(extra_feature_registry),
        "extra_feature_registry": extra_feature_registry[:50],
        "concepts_used": concepts_used,
        "missing_concepts_count": len(missing_concepts),
        "missing_concepts": missing_concepts,
        "features_missing_concept_count": len(features_missing_concept),
        "features_missing_concept": features_missing_concept[:50],
        "explanation_blocked_feature_count": len(explanation_blocked_features),
        "explanation_blocked_features": explanation_blocked_features[:50],
        "explanation_limited_feature_count": len(explanation_limited_features),
        "explanation_limited_features": explanation_limited_features[:50],
        "sensitive_feature_count": len(sensitive_features),
        "sensitive_features": sensitive_features[:50],
        "suspicious_metadata_count": len(suspicious_metadata),
        "suspicious_metadata": suspicious_metadata[:50],
        "status": "passed" if not errors else "blocked",
        "errors": errors,
    }


def validate_final_matrix(matrix: pd.DataFrame, expected_rows: int) -> dict[str, Any]:
    errors = []

    if "SK_ID_CURR" not in matrix.columns:
        errors.append("SK_ID_CURR missing from feature_matrix_full")
        duplicate_ids = None
    else:
        duplicate_ids = int(matrix["SK_ID_CURR"].duplicated().sum())

    row_count = len(matrix)
    column_count = len(matrix.columns)

    forbidden_found = sorted([c for c in FORBIDDEN_IN_FEATURE_MATRIX if c in matrix.columns])

    inf_count = count_inf(matrix)

    if row_count != expected_rows:
        errors.append(f"row count mismatch: expected {expected_rows}, got {row_count}")

    if duplicate_ids is not None and duplicate_ids > 0:
        errors.append(f"duplicate SK_ID_CURR: {duplicate_ids}")

    if forbidden_found:
        errors.append(f"forbidden columns found in feature_matrix_full: {forbidden_found}")

    if inf_count > 0:
        errors.append(f"inf/-inf values found: {inf_count}")

    feature_columns = [
        c for c in matrix.columns
        if c != "SK_ID_CURR"
    ]

    numeric_features = [
        c for c in feature_columns
        if pd.api.types.is_numeric_dtype(matrix[c])
    ]

    categorical_features = [
        c for c in feature_columns
        if not pd.api.types.is_numeric_dtype(matrix[c])
    ]

    binary_features = [
        c for c in feature_columns
        if c.startswith("has_") or c.endswith("_flag") or c.endswith("_abnormal")
    ]

    all_null_features = [
        c for c in feature_columns
        if matrix[c].isna().all()
    ]

    constant_features = [
        c for c in feature_columns
        if matrix[c].nunique(dropna=False) <= 1
    ]

    missing_rates = matrix[feature_columns].isna().mean().sort_values(ascending=False)
    top_missing_features = [
        {
            "feature_name": str(feature),
            "missing_rate": float(rate),
        }
        for feature, rate in missing_rates.head(30).items()
    ]

    return {
        "row_count": int(row_count),
        "column_count": int(column_count),
        "feature_count": int(len(feature_columns)),
        "numeric_feature_count": int(len(numeric_features)),
        "categorical_feature_count": int(len(categorical_features)),
        "binary_feature_count": int(len(binary_features)),
        "duplicate_sk_id_curr": duplicate_ids,
        "forbidden_columns_found": forbidden_found,
        "inf_count": int(inf_count),
        "all_null_feature_count": int(len(all_null_features)),
        "all_null_features": all_null_features[:50],
        "constant_feature_count": int(len(constant_features)),
        "constant_features": constant_features[:50],
        "top_missing_features": top_missing_features,
        "status": "passed" if not errors else "blocked",
        "errors": errors,
    }


def save_yaml(data: dict[str, Any], path: Path) -> None:
    # PyYAML chỉ cần khi ghi registry; import core/validation không nên phụ thuộc writer.
    import yaml

    path.write_text(
        yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )


def write_feature_matrix_registry_report(
    group_stats: list[dict[str, Any]],
    final_matrix_stats: dict[str, Any],
    target_stats: dict[str, Any],
    registry_stats: dict[str, Any],
) -> None:
    report_path = REPORT_DIR / "feature_matrix_registry_report.md"

    md = []

    md.append("# Feature Matrix and Registry Report\n")
    md.append(f"Created at: `{now_iso()}`\n")

    md.append("## Purpose\n")
    md.append(
        "Batch C merges all Batch B customer-level feature groups into one official model feature matrix, "
        "separates the target, and builds concept/feature registries for later preprocessing, modeling, SHAP, and LLM explanation.\n"
    )

    md.append("## Feature Group Merge Summary\n")
    md.append("| Feature group | Rows | Columns | Features | Duplicate SK_ID_CURR | Inf count | Status |")
    md.append("|---|---:|---:|---:|---:|---:|---|")

    for s in group_stats:
        md.append(
            f"| {s['group_name']} | {s['rows']} | {s['columns']} | "
            f"{s['feature_count']} | {s['duplicate_sk_id_curr']} | "
            f"{s['inf_count']} | `{s['status']}` |"
        )

    md.append("\n## Final Feature Matrix\n")
    md.append(f"- Rows: `{final_matrix_stats['row_count']}`")
    md.append(f"- Columns: `{final_matrix_stats['column_count']}`")
    md.append(f"- Model feature count excluding `SK_ID_CURR`: `{final_matrix_stats['feature_count']}`")
    md.append(f"- Numeric features: `{final_matrix_stats['numeric_feature_count']}`")
    md.append(f"- Categorical features: `{final_matrix_stats['categorical_feature_count']}`")
    md.append(f"- Binary indicator features: `{final_matrix_stats['binary_feature_count']}`")
    md.append(f"- Duplicate `SK_ID_CURR`: `{final_matrix_stats['duplicate_sk_id_curr']}`")
    md.append(f"- Forbidden columns found: `{final_matrix_stats['forbidden_columns_found']}`")
    md.append(f"- Inf/-inf count: `{final_matrix_stats['inf_count']}`")
    md.append(f"- All-null feature count: `{final_matrix_stats['all_null_feature_count']}`")
    md.append(f"- Constant feature count: `{final_matrix_stats['constant_feature_count']}`")
    md.append(f"- Matrix status: `{final_matrix_stats['status']}`\n")

    md.append("## Target File\n")
    md.append(f"- Rows: `{target_stats['row_count']}`")
    md.append(f"- Columns: `{target_stats['column_count']}`")
    md.append(f"- Duplicate `SK_ID_CURR`: `{target_stats['duplicate_sk_id_curr']}`")
    md.append(f"- Missing TARGET: `{target_stats['missing_target']}`")
    md.append(f"- TARGET values: `{target_stats['target_values']}`")
    md.append(f"- TARGET positive count: `{target_stats['target_positive_count']}`")
    md.append(f"- TARGET negative count: `{target_stats['target_negative_count']}`")
    md.append(f"- TARGET positive rate: `{target_stats['target_positive_rate']:.6f}`")
    md.append(f"- Target status: `{target_stats['status']}`\n")

    md.append("## Registry Validation\n")
    md.append(f"- Feature count: `{registry_stats['feature_count']}`")
    md.append(f"- Feature registry entries: `{registry_stats['feature_registry_entry_count']}`")
    md.append(f"- Missing feature registry entries: `{registry_stats['missing_feature_registry_count']}`")
    md.append(f"- Extra feature registry entries: `{registry_stats['extra_feature_registry_count']}`")
    md.append(f"- Concepts used: `{registry_stats['concepts_used']}`")
    md.append(f"- Missing concepts: `{registry_stats['missing_concepts_count']}`")
    md.append(f"- Features missing concept: `{registry_stats['features_missing_concept_count']}`")
    md.append(f"- Explanation-blocked features: `{registry_stats['explanation_blocked_feature_count']}`")
    md.append(f"- Explanation-limited features: `{registry_stats['explanation_limited_feature_count']}`")
    md.append(f"- Sensitive features: `{registry_stats['sensitive_feature_count']}`")
    md.append(f"- Suspicious metadata count: `{registry_stats['suspicious_metadata_count']}`")
    md.append(f"- Registry status: `{registry_stats['status']}`\n")

    md.append("## Top Missing Features\n")
    md.append("| Feature | Missing rate |")
    md.append("|---|---:|")
    for item in final_matrix_stats["top_missing_features"]:
        md.append(f"| `{item['feature_name']}` | `{item['missing_rate']:.6f}` |")

    md.append("\n## Output Files\n")
    md.append("- `data/processed/feature_matrix_full.parquet`")
    md.append("- `data/processed/target_full.parquet`")
    md.append("- `ml/registry/concept_registry.yaml`")
    md.append("- `ml/registry/feature_registry.yaml`")
    md.append("- `ml/registry/feature_registry.csv`")
    md.append("- `data/reports/feature_matrix_registry_report.md`")
    md.append("- `data/reports/batch_c_feature_matrix_registry_summary.md`")
    md.append("- `data/manifests/batch_c_feature_matrix_registry_summary.json`\n")

    md.append("## Validation Rules\n")
    md.append("- `feature_matrix_full.parquet` must contain `SK_ID_CURR`.")
    md.append("- `feature_matrix_full.parquet` must not contain `TARGET`.")
    md.append("- `feature_matrix_full.parquet` must not contain `SK_ID_BUREAU` or `SK_ID_PREV`.")
    md.append("- `feature_matrix_full.parquet` must have exactly one row per `SK_ID_CURR`.")
    md.append("- `target_full.parquet` must contain only `SK_ID_CURR` and `TARGET`.")
    md.append("- No `inf` or `-inf` should remain in the feature matrix.")
    md.append("- Missing values are allowed at this stage; imputation happens after train/valid/test split.")
    md.append("- Categorical strings are allowed at this stage; encoding happens after train/valid/test split.")
    md.append("- Registry value_type/unit/formatting_rule are checked to avoid obvious metadata mistakes.\n")

    md.append("## Notes for Next Stage\n")
    md.append(
        "Batch D can now perform leakage checks and train/validation/test split. "
        "No preprocessing, scaling, one-hot encoding, model training, SHAP, or LLM explanation has been performed in Batch C."
    )

    matrix_errors = final_matrix_stats["errors"]
    target_errors = target_stats["errors"]
    registry_errors = registry_stats["errors"]

    if matrix_errors or target_errors or registry_errors:
        md.append("\n## Blocking Errors\n")

        if matrix_errors:
            md.append("### Matrix Errors")
            for err in matrix_errors:
                md.append(f"- {err}")

        if target_errors:
            md.append("### Target Errors")
            for err in target_errors:
                md.append(f"- {err}")

        if registry_errors:
            md.append("### Registry Errors")
            for err in registry_errors:
                md.append(f"- {err}")

        if registry_stats["suspicious_metadata"]:
            md.append("### Suspicious Metadata Examples")
            for item in registry_stats["suspicious_metadata"]:
                md.append(f"- {item}")

    report_path.write_text("\n".join(md), encoding="utf-8")


def write_batch_c_summary(
    final_matrix_stats: dict[str, Any],
    target_stats: dict[str, Any],
    registry_stats: dict[str, Any],
    group_stats: list[dict[str, Any]],
) -> None:
    all_passed = (
        final_matrix_stats["status"] == "passed"
        and target_stats["status"] == "passed"
        and registry_stats["status"] == "passed"
        and all(s["status"] == "merged" for s in group_stats)
    )

    completed_before = 13
    batch_c_steps = 3
    completed = completed_before + (batch_c_steps if all_passed else 0)
    total = 20
    remaining = total - completed

    summary = {
        "batch_name": "batch_c_feature_matrix_registry_layer",
        "created_at": now_iso(),
        "assumption": "Batch A Raw Audit Layer and Batch B Feature Engineering Layer were already completed.",
        "pipeline_group": "Batch C - Feature Matrix + Registry Layer",
        "pipeline_group_status": "feature_matrix_registry_layer_completed" if all_passed else "blocked",
        "technical_steps_completed": completed,
        "technical_steps_total": total,
        "technical_steps_remaining": remaining,
        "final_matrix_stats": final_matrix_stats,
        "target_stats": target_stats,
        "registry_stats": registry_stats,
        "feature_group_merge_stats": group_stats,
        "outputs": [
            "data/processed/feature_matrix_full.parquet",
            "data/processed/target_full.parquet",
            "ml/registry/concept_registry.yaml",
            "ml/registry/feature_registry.yaml",
            "ml/registry/feature_registry.csv",
            "data/reports/feature_matrix_registry_report.md",
            "data/reports/batch_c_feature_matrix_registry_summary.md",
            "data/manifests/batch_c_feature_matrix_registry_summary.json",
        ],
        "next_group": "Batch D - Leakage + Split Layer" if all_passed else None,
    }

    manifest_path = MANIFEST_DIR / "batch_c_feature_matrix_registry_summary.json"
    manifest_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = []

    md.append("# Batch C Summary — Feature Matrix + Registry Layer\n")
    md.append("Assumption: Batch A and Batch B were already completed.\n")

    md.append("## Batch Status\n")
    md.append(f"- Status: `{'feature_matrix_registry_layer_completed' if all_passed else 'blocked'}`")
    md.append(f"- Technical steps completed: `{completed}/{total}`")
    md.append(f"- Technical steps remaining: `{remaining}/{total}`")

    if all_passed:
        md.append("- Next group: `Batch D - Leakage + Split Layer`")
    else:
        md.append("- Next group: blocked until errors are fixed")

    md.append("\n## Final Feature Matrix\n")
    md.append(f"- Rows: `{final_matrix_stats['row_count']}`")
    md.append(f"- Columns: `{final_matrix_stats['column_count']}`")
    md.append(f"- Features excluding `SK_ID_CURR`: `{final_matrix_stats['feature_count']}`")
    md.append(f"- Numeric features: `{final_matrix_stats['numeric_feature_count']}`")
    md.append(f"- Categorical features: `{final_matrix_stats['categorical_feature_count']}`")
    md.append(f"- Binary features: `{final_matrix_stats['binary_feature_count']}`")
    md.append(f"- Duplicate SK_ID_CURR: `{final_matrix_stats['duplicate_sk_id_curr']}`")
    md.append(f"- Forbidden columns found: `{final_matrix_stats['forbidden_columns_found']}`")
    md.append(f"- Inf/-inf count: `{final_matrix_stats['inf_count']}`")
    md.append(f"- Status: `{final_matrix_stats['status']}`")

    md.append("\n## Target\n")
    md.append(f"- Rows: `{target_stats['row_count']}`")
    md.append(f"- TARGET positive rate: `{target_stats['target_positive_rate']:.6f}`")
    md.append(f"- Status: `{target_stats['status']}`")

    md.append("\n## Registry\n")
    md.append(f"- Feature registry entries: `{registry_stats['feature_registry_entry_count']}`")
    md.append(f"- Missing feature registry entries: `{registry_stats['missing_feature_registry_count']}`")
    md.append(f"- Missing concepts: `{registry_stats['missing_concepts_count']}`")
    md.append(f"- Explanation-blocked features: `{registry_stats['explanation_blocked_feature_count']}`")
    md.append(f"- Explanation-limited features: `{registry_stats['explanation_limited_feature_count']}`")
    md.append(f"- Sensitive features: `{registry_stats['sensitive_feature_count']}`")
    md.append(f"- Suspicious metadata: `{registry_stats['suspicious_metadata_count']}`")
    md.append(f"- Status: `{registry_stats['status']}`")

    md.append("\n## Output Files\n")
    for output in summary["outputs"]:
        md.append(f"- `{output}`")

    summary_report_path = REPORT_DIR / "batch_c_feature_matrix_registry_summary.md"
    summary_report_path.write_text("\n".join(md), encoding="utf-8")
