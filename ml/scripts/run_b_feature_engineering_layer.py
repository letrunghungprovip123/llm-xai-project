from __future__ import annotations

import gc
import json
from pathlib import Path
from datetime import datetime
from typing import Callable

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
REPORT_DIR = PROJECT_ROOT / "data" / "reports"
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"

INTERIM_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_RAW_FILES = [
    "application_train.csv",
    "bureau.csv",
    "bureau_balance.csv",
    "previous_application.csv",
    "installments_payments.csv",
    "POS_CASH_balance.csv",
    "credit_card_balance.csv",
]

FORBIDDEN_OUTPUT_COLUMNS = {
    "TARGET",
    "SK_ID_BUREAU",
    "SK_ID_PREV",
}

RECENT_INSTALLMENT_N = 12


def safe_divide(
    numerator: pd.Series,
    denominator: pd.Series,
    require_positive_denominator: bool = True,
) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")

    result = pd.Series(np.nan, index=num.index, dtype="float64")

    if require_positive_denominator:
        valid = num.notna() & den.notna() & (den > 0)
    else:
        valid = num.notna() & den.notna() & (den != 0)

    result.loc[valid] = num.loc[valid] / den.loc[valid]
    return result.replace([np.inf, -np.inf], np.nan)


def replace_inf_with_nan(df: pd.DataFrame) -> pd.DataFrame:
    return df.replace([np.inf, -np.inf], np.nan)


def count_inf(df: pd.DataFrame) -> int:
    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.empty:
        return 0
    return int(np.isinf(numeric_df.to_numpy()).sum())


def ensure_raw_files_exist() -> None:
    missing = []
    for filename in REQUIRED_RAW_FILES:
        if not (RAW_DIR / filename).exists():
            missing.append(filename)

    if missing:
        raise FileNotFoundError(f"Missing raw files in data/raw/: {missing}")


def load_base_customers() -> pd.DataFrame:
    return pd.read_csv(RAW_DIR / "application_train.csv", usecols=["SK_ID_CURR"])


def merge_to_base_customers(
    base_customers: pd.DataFrame,
    feature_df: pd.DataFrame,
    history_col: str | None,
    zero_fill_cols: list[str] | None = None,
) -> pd.DataFrame:
    out = base_customers.merge(feature_df, on="SK_ID_CURR", how="left")

    if history_col is not None:
        if history_col not in out.columns:
            out[history_col] = 0
        out[history_col] = out[history_col].fillna(0).astype("int8")

    if zero_fill_cols:
        for col in zero_fill_cols:
            if col in out.columns:
                out[col] = out[col].fillna(0)

    return out


def validate_feature_group(df: pd.DataFrame, group_name: str) -> dict:
    errors = []

    if "SK_ID_CURR" not in df.columns:
        errors.append("Missing SK_ID_CURR")
        duplicate_ids = None
    else:
        duplicate_ids = int(df["SK_ID_CURR"].duplicated().sum())
        if duplicate_ids > 0:
            errors.append(f"Duplicate SK_ID_CURR rows: {duplicate_ids}")

    forbidden_found = sorted([c for c in FORBIDDEN_OUTPUT_COLUMNS if c in df.columns])
    if forbidden_found:
        errors.append(f"Forbidden columns found: {forbidden_found}")

    inf_count_before_clean = count_inf(df)
    if inf_count_before_clean > 0:
        errors.append(f"inf/-inf values found before cleaning: {inf_count_before_clean}")

    checked = replace_inf_with_nan(df)

    feature_cols = [c for c in checked.columns if c != "SK_ID_CURR"]
    all_null_features = [c for c in feature_cols if checked[c].isna().all()]
    constant_features = [c for c in feature_cols if checked[c].nunique(dropna=False) <= 1]

    return {
        "group_name": group_name,
        "row_count": int(len(checked)),
        "column_count": int(len(checked.columns)),
        "feature_count_excluding_id": int(len(feature_cols)),
        "duplicate_sk_id_curr": duplicate_ids,
        "forbidden_columns_found": forbidden_found,
        "inf_count_before_cleaning": inf_count_before_clean,
        "all_null_feature_count": len(all_null_features),
        "all_null_features": all_null_features[:50],
        "constant_feature_count": len(constant_features),
        "constant_features": constant_features[:50],
        "status": "passed" if not errors else "blocked",
        "errors": errors,
    }


def save_feature_group(df: pd.DataFrame, output_filename: str, group_name: str) -> dict:
    df = replace_inf_with_nan(df)

    out_path = INTERIM_DIR / output_filename
    df.to_parquet(out_path, index=False)

    stats = validate_feature_group(df, group_name)
    stats["output_path"] = str(out_path.relative_to(PROJECT_ROOT))
    stats["file_size_mb"] = round(out_path.stat().st_size / (1024 * 1024), 2)

    return stats


def build_application_features(base_customers: pd.DataFrame) -> pd.DataFrame:
    print("[Batch B] Building application_features.parquet ...")

    usecols = [
        "SK_ID_CURR",
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
        "DAYS_BIRTH",
        "DAYS_EMPLOYED",
        "DAYS_REGISTRATION",
        "DAYS_ID_PUBLISH",
        "EXT_SOURCE_1",
        "EXT_SOURCE_2",
        "EXT_SOURCE_3",
    ]

    df = pd.read_csv(RAW_DIR / "application_train.csv", usecols=usecols)

    df["days_employed_abnormal"] = (
        (df["DAYS_EMPLOYED"] == 365243) | (df["DAYS_EMPLOYED"] >= 0)
    ).astype("int8")

    days_employed_clean = df["DAYS_EMPLOYED"].mask(
        df["days_employed_abnormal"] == 1,
        np.nan,
    )

    df["age_years"] = safe_divide(-df["DAYS_BIRTH"], pd.Series(365.25, index=df.index))
    df["employment_years"] = safe_divide(-days_employed_clean, pd.Series(365.25, index=df.index))
    df["registration_years"] = safe_divide(-df["DAYS_REGISTRATION"], pd.Series(365.25, index=df.index))
    df["id_publish_years"] = safe_divide(-df["DAYS_ID_PUBLISH"], pd.Series(365.25, index=df.index))

    df["credit_to_income_ratio"] = safe_divide(df["AMT_CREDIT"], df["AMT_INCOME_TOTAL"])
    df["annuity_to_income_ratio"] = safe_divide(df["AMT_ANNUITY"], df["AMT_INCOME_TOTAL"])
    df["goods_price_to_income_ratio"] = safe_divide(df["AMT_GOODS_PRICE"], df["AMT_INCOME_TOTAL"])
    df["annuity_to_credit_ratio"] = safe_divide(df["AMT_ANNUITY"], df["AMT_CREDIT"])
    df["credit_to_goods_price_ratio"] = safe_divide(df["AMT_CREDIT"], df["AMT_GOODS_PRICE"])
    df["income_per_family_member"] = safe_divide(df["AMT_INCOME_TOTAL"], df["CNT_FAM_MEMBERS"])

    ext_cols = ["EXT_SOURCE_1", "EXT_SOURCE_2", "EXT_SOURCE_3"]
    df["ext_source_mean"] = df[ext_cols].mean(axis=1, skipna=True)
    df["ext_source_min"] = df[ext_cols].min(axis=1, skipna=True)
    df["ext_source_max"] = df[ext_cols].max(axis=1, skipna=True)
    df["ext_source_std"] = df[ext_cols].std(axis=1, skipna=True)
    df["ext_source_missing_count"] = df[ext_cols].isna().sum(axis=1).astype("int8")

    df = df.drop(
        columns=[
            "DAYS_BIRTH",
            "DAYS_EMPLOYED",
            "DAYS_REGISTRATION",
            "DAYS_ID_PUBLISH",
        ]
    )

    return df


def build_bureau_features(base_customers: pd.DataFrame) -> pd.DataFrame:
    print("[Batch B] Building bureau_features.parquet ...")

    df = pd.read_csv(RAW_DIR / "bureau.csv")

    df["bureau_active_loan_flag"] = (df["CREDIT_ACTIVE"] == "Active").astype("int8")
    df["bureau_closed_loan_flag"] = (df["CREDIT_ACTIVE"] == "Closed").astype("int8")
    df["bureau_sold_loan_flag"] = (df["CREDIT_ACTIVE"] == "Sold").astype("int8")
    df["bureau_bad_debt_flag"] = (df["CREDIT_ACTIVE"] == "Bad debt").astype("int8")
    df["bureau_overdue_flag"] = (pd.to_numeric(df["CREDIT_DAY_OVERDUE"], errors="coerce") > 0).astype("int8")
    df["bureau_recent_loan_flag"] = (pd.to_numeric(df["DAYS_CREDIT"], errors="coerce") >= -365).astype("int8")

    agg = df.groupby("SK_ID_CURR").agg(
        bureau_record_count=("SK_ID_BUREAU", "count"),
        bureau_total_loans=("SK_ID_BUREAU", "count"),
        bureau_active_loan_count=("bureau_active_loan_flag", "sum"),
        bureau_closed_loan_count=("bureau_closed_loan_flag", "sum"),
        bureau_sold_loan_count=("bureau_sold_loan_flag", "sum"),
        bureau_bad_debt_count=("bureau_bad_debt_flag", "sum"),
        bureau_overdue_count=("bureau_overdue_flag", "sum"),
        bureau_max_days_credit_overdue=("CREDIT_DAY_OVERDUE", "max"),
        bureau_avg_days_credit_overdue=("CREDIT_DAY_OVERDUE", "mean"),
        bureau_credit_sum_total=("AMT_CREDIT_SUM", "sum"),
        bureau_credit_sum_mean=("AMT_CREDIT_SUM", "mean"),
        bureau_credit_sum_max=("AMT_CREDIT_SUM", "max"),
        bureau_credit_debt_total=("AMT_CREDIT_SUM_DEBT", "sum"),
        bureau_credit_debt_mean=("AMT_CREDIT_SUM_DEBT", "mean"),
        bureau_credit_debt_max=("AMT_CREDIT_SUM_DEBT", "max"),
        bureau_credit_limit_total=("AMT_CREDIT_SUM_LIMIT", "sum"),
        bureau_credit_limit_mean=("AMT_CREDIT_SUM_LIMIT", "mean"),
        bureau_overdue_amount_total=("AMT_CREDIT_SUM_OVERDUE", "sum"),
        bureau_overdue_amount_max=("AMT_CREDIT_SUM_OVERDUE", "max"),
        bureau_avg_days_credit=("DAYS_CREDIT", "mean"),
        bureau_min_days_credit=("DAYS_CREDIT", "min"),
        bureau_max_days_credit=("DAYS_CREDIT", "max"),
        bureau_recent_loan_count=("bureau_recent_loan_flag", "sum"),
    ).reset_index()

    agg["bureau_debt_to_credit_ratio"] = safe_divide(
        agg["bureau_credit_debt_total"],
        agg["bureau_credit_sum_total"],
    )

    agg["bureau_long_history_months"] = safe_divide(
        -agg["bureau_min_days_credit"],
        pd.Series(30.0, index=agg.index),
    )

    agg["has_bureau_history"] = 1

    zero_fill_cols = [
        "bureau_record_count",
        "bureau_total_loans",
        "bureau_active_loan_count",
        "bureau_closed_loan_count",
        "bureau_sold_loan_count",
        "bureau_bad_debt_count",
        "bureau_overdue_count",
        "bureau_credit_sum_total",
        "bureau_credit_debt_total",
        "bureau_credit_limit_total",
        "bureau_overdue_amount_total",
        "bureau_recent_loan_count",
    ]

    return merge_to_base_customers(
        base_customers,
        agg,
        history_col="has_bureau_history",
        zero_fill_cols=zero_fill_cols,
    )


def build_bureau_balance_features(base_customers: pd.DataFrame) -> pd.DataFrame:
    print("[Batch B] Building bureau_balance_features.parquet ...")

    bureau_map = pd.read_csv(
        RAW_DIR / "bureau.csv",
        usecols=["SK_ID_BUREAU", "SK_ID_CURR"],
    )

    bb = pd.read_csv(RAW_DIR / "bureau_balance.csv")

    status_str = bb["STATUS"].astype(str)

    bb["bb_good_status"] = (status_str == "0").astype("int8")
    bb["bb_bad_status"] = status_str.isin(["1", "2", "3", "4", "5"]).astype("int8")
    bb["bb_closed_status"] = (status_str == "C").astype("int8")
    bb["bb_unknown_status"] = (status_str == "X").astype("int8")

    status_num = pd.to_numeric(bb["STATUS"], errors="coerce")
    status_num = status_num.mask(status_str == "C", 0)
    bb["bb_status_numeric"] = status_num

    bb["bb_recent_month"] = (pd.to_numeric(bb["MONTHS_BALANCE"], errors="coerce") >= -12).astype("int8")
    bb["bb_recent_bad_status"] = ((bb["bb_recent_month"] == 1) & (bb["bb_bad_status"] == 1)).astype("int8")

    by_bureau = bb.groupby("SK_ID_BUREAU").agg(
        bureau_balance_months_observed=("MONTHS_BALANCE", "count"),
        bureau_balance_good_status_count=("bb_good_status", "sum"),
        bureau_balance_bad_status_count=("bb_bad_status", "sum"),
        bureau_balance_closed_status_count=("bb_closed_status", "sum"),
        bureau_balance_unknown_status_count=("bb_unknown_status", "sum"),
        bureau_balance_recent_month_count=("bb_recent_month", "sum"),
        bureau_balance_recent_bad_status_count=("bb_recent_bad_status", "sum"),
        bureau_balance_max_status_numeric=("bb_status_numeric", "max"),
        bureau_balance_avg_status_numeric=("bb_status_numeric", "mean"),
    ).reset_index()

    by_bureau = by_bureau.merge(bureau_map, on="SK_ID_BUREAU", how="left")
    by_bureau = by_bureau.dropna(subset=["SK_ID_CURR"])

    by_customer = by_bureau.groupby("SK_ID_CURR").agg(
        bureau_balance_months_observed=("bureau_balance_months_observed", "sum"),
        bureau_balance_good_status_count=("bureau_balance_good_status_count", "sum"),
        bureau_balance_bad_status_count=("bureau_balance_bad_status_count", "sum"),
        bureau_balance_closed_status_count=("bureau_balance_closed_status_count", "sum"),
        bureau_balance_unknown_status_count=("bureau_balance_unknown_status_count", "sum"),
        bureau_balance_recent_month_count=("bureau_balance_recent_month_count", "sum"),
        bureau_balance_recent_bad_status_count=("bureau_balance_recent_bad_status_count", "sum"),
        bureau_balance_max_status_numeric=("bureau_balance_max_status_numeric", "max"),
        bureau_balance_avg_status_numeric=("bureau_balance_avg_status_numeric", "mean"),
    ).reset_index()

    by_customer["bureau_balance_bad_status_ratio"] = safe_divide(
        by_customer["bureau_balance_bad_status_count"],
        by_customer["bureau_balance_months_observed"],
    )

    by_customer["bureau_balance_recent_bad_status_ratio"] = safe_divide(
        by_customer["bureau_balance_recent_bad_status_count"],
        by_customer["bureau_balance_recent_month_count"],
    )

    by_customer["has_bureau_balance_history"] = 1

    zero_fill_cols = [
        "bureau_balance_months_observed",
        "bureau_balance_good_status_count",
        "bureau_balance_bad_status_count",
        "bureau_balance_closed_status_count",
        "bureau_balance_unknown_status_count",
        "bureau_balance_recent_month_count",
        "bureau_balance_recent_bad_status_count",
    ]

    return merge_to_base_customers(
        base_customers,
        by_customer,
        history_col="has_bureau_balance_history",
        zero_fill_cols=zero_fill_cols,
    )


def build_previous_application_features(base_customers: pd.DataFrame) -> pd.DataFrame:
    print("[Batch B] Building previous_application_features.parquet ...")

    df = pd.read_csv(RAW_DIR / "previous_application.csv")

    status = df["NAME_CONTRACT_STATUS"].astype(str)
    contract_type = df["NAME_CONTRACT_TYPE"].astype(str)

    df["previous_approved_flag"] = (status == "Approved").astype("int8")
    df["previous_refused_flag"] = (status == "Refused").astype("int8")
    df["previous_canceled_flag"] = (status == "Canceled").astype("int8")
    df["previous_unused_offer_flag"] = (status == "Unused offer").astype("int8")

    df["previous_cash_loan_flag"] = (contract_type == "Cash loans").astype("int8")
    df["previous_consumer_loan_flag"] = (contract_type == "Consumer loans").astype("int8")
    df["previous_revolving_loan_flag"] = (contract_type == "Revolving loans").astype("int8")

    df["previous_recent_application_flag"] = (pd.to_numeric(df["DAYS_DECISION"], errors="coerce") >= -365).astype("int8")

    agg = df.groupby("SK_ID_CURR").agg(
        previous_application_count=("SK_ID_PREV", "count"),
        previous_approved_count=("previous_approved_flag", "sum"),
        previous_refused_count=("previous_refused_flag", "sum"),
        previous_canceled_count=("previous_canceled_flag", "sum"),
        previous_unused_offer_count=("previous_unused_offer_flag", "sum"),
        previous_avg_credit_amount=("AMT_CREDIT", "mean"),
        previous_max_credit_amount=("AMT_CREDIT", "max"),
        previous_total_credit_amount=("AMT_CREDIT", "sum"),
        previous_avg_annuity=("AMT_ANNUITY", "mean"),
        previous_max_annuity=("AMT_ANNUITY", "max"),
        previous_avg_application_amount=("AMT_APPLICATION", "mean"),
        previous_total_application_amount=("AMT_APPLICATION", "sum"),
        previous_avg_days_decision=("DAYS_DECISION", "mean"),
        previous_recent_application_count=("previous_recent_application_flag", "sum"),
        previous_cash_loan_count=("previous_cash_loan_flag", "sum"),
        previous_consumer_loan_count=("previous_consumer_loan_flag", "sum"),
        previous_revolving_loan_count=("previous_revolving_loan_flag", "sum"),
    ).reset_index()

    agg["previous_approval_ratio"] = safe_divide(
        agg["previous_approved_count"],
        agg["previous_application_count"],
    )

    agg["previous_refusal_ratio"] = safe_divide(
        agg["previous_refused_count"],
        agg["previous_application_count"],
    )

    agg["previous_canceled_ratio"] = safe_divide(
        agg["previous_canceled_count"],
        agg["previous_application_count"],
    )

    agg["previous_credit_to_application_ratio"] = safe_divide(
        agg["previous_total_credit_amount"],
        agg["previous_total_application_amount"],
    )

    agg["has_previous_application_history"] = 1

    zero_fill_cols = [
        "previous_application_count",
        "previous_approved_count",
        "previous_refused_count",
        "previous_canceled_count",
        "previous_unused_offer_count",
        "previous_total_credit_amount",
        "previous_total_application_amount",
        "previous_recent_application_count",
        "previous_cash_loan_count",
        "previous_consumer_loan_count",
        "previous_revolving_loan_count",
    ]

    return merge_to_base_customers(
        base_customers,
        agg,
        history_col="has_previous_application_history",
        zero_fill_cols=zero_fill_cols,
    )


def build_installments_features(base_customers: pd.DataFrame) -> pd.DataFrame:
    print("[Batch B] Building installments_features.parquet ...")

    df = pd.read_csv(RAW_DIR / "installments_payments.csv")

    df["days_late"] = (
        pd.to_numeric(df["DAYS_ENTRY_PAYMENT"], errors="coerce")
        - pd.to_numeric(df["DAYS_INSTALMENT"], errors="coerce")
    )

    df["days_early"] = (
        pd.to_numeric(df["DAYS_INSTALMENT"], errors="coerce")
        - pd.to_numeric(df["DAYS_ENTRY_PAYMENT"], errors="coerce")
    )

    df["installment_is_late"] = (df["days_late"] > 0).astype("int8")
    df["installment_is_early"] = (df["days_early"] > 0).astype("int8")

    df["days_late_positive"] = df["days_late"].where(df["days_late"] > 0, np.nan)
    df["days_early_positive"] = df["days_early"].where(df["days_early"] > 0, np.nan)

    df["payment_ratio"] = safe_divide(df["AMT_PAYMENT"], df["AMT_INSTALMENT"])

    df["installment_is_underpaid"] = (df["payment_ratio"] < 1).fillna(False).astype("int8")
    df["installment_is_fully_paid"] = (df["payment_ratio"] >= 1).fillna(False).astype("int8")

    agg = df.groupby("SK_ID_CURR").agg(
        installment_count=("SK_ID_PREV", "count"),
        installment_late_payment_count=("installment_is_late", "sum"),
        installment_early_payment_count=("installment_is_early", "sum"),
        installment_avg_days_late=("days_late_positive", "mean"),
        installment_max_days_late=("days_late_positive", "max"),
        installment_sum_days_late=("days_late_positive", "sum"),
        installment_avg_days_early=("days_early_positive", "mean"),
        installment_max_days_early=("days_early_positive", "max"),
        installment_underpayment_count=("installment_is_underpaid", "sum"),
        installment_fully_paid_count=("installment_is_fully_paid", "sum"),
        installment_payment_ratio_avg=("payment_ratio", "mean"),
        installment_payment_ratio_min=("payment_ratio", "min"),
        installment_payment_ratio_max=("payment_ratio", "max"),
        installment_payment_ratio_std=("payment_ratio", "std"),
        installment_total_expected_amount=("AMT_INSTALMENT", "sum"),
        installment_total_paid_amount=("AMT_PAYMENT", "sum"),
    ).reset_index()

    agg["installment_late_payment_ratio"] = safe_divide(
        agg["installment_late_payment_count"],
        agg["installment_count"],
    )

    agg["installment_early_payment_ratio"] = safe_divide(
        agg["installment_early_payment_count"],
        agg["installment_count"],
    )

    agg["installment_underpayment_ratio"] = safe_divide(
        agg["installment_underpayment_count"],
        agg["installment_count"],
    )

    agg["installment_total_payment_gap"] = (
        agg["installment_total_expected_amount"] - agg["installment_total_paid_amount"]
    )

    print("[Batch B] Computing recent installment behavior using latest 12 installments per customer ...")

    recent = (
        df.sort_values(["SK_ID_CURR", "DAYS_INSTALMENT"], kind="mergesort")
        .groupby("SK_ID_CURR", as_index=False)
        .tail(RECENT_INSTALLMENT_N)
    )

    recent_agg = recent.groupby("SK_ID_CURR").agg(
        installment_recent_count=("SK_ID_PREV", "count"),
        installment_recent_late_payment_count=("installment_is_late", "sum"),
        installment_recent_payment_ratio_avg=("payment_ratio", "mean"),
        installment_recent_underpayment_count=("installment_is_underpaid", "sum"),
    ).reset_index()

    recent_agg["installment_recent_late_payment_ratio"] = safe_divide(
        recent_agg["installment_recent_late_payment_count"],
        recent_agg["installment_recent_count"],
    )

    recent_agg["installment_recent_underpayment_ratio"] = safe_divide(
        recent_agg["installment_recent_underpayment_count"],
        recent_agg["installment_recent_count"],
    )

    agg = agg.merge(recent_agg, on="SK_ID_CURR", how="left")
    agg["has_installment_history"] = 1

    zero_fill_cols = [
        "installment_count",
        "installment_late_payment_count",
        "installment_early_payment_count",
        "installment_sum_days_late",
        "installment_underpayment_count",
        "installment_fully_paid_count",
        "installment_total_expected_amount",
        "installment_total_paid_amount",
        "installment_total_payment_gap",
        "installment_recent_count",
        "installment_recent_late_payment_count",
        "installment_recent_underpayment_count",
    ]

    return merge_to_base_customers(
        base_customers,
        agg,
        history_col="has_installment_history",
        zero_fill_cols=zero_fill_cols,
    )


def build_pos_cash_features(base_customers: pd.DataFrame) -> pd.DataFrame:
    print("[Batch B] Building pos_cash_features.parquet ...")

    df = pd.read_csv(RAW_DIR / "POS_CASH_balance.csv")

    status = df["NAME_CONTRACT_STATUS"].astype(str)

    df["pos_cash_dpd_flag"] = (pd.to_numeric(df["SK_DPD"], errors="coerce") > 0).astype("int8")
    df["pos_cash_def_dpd_flag"] = (pd.to_numeric(df["SK_DPD_DEF"], errors="coerce") > 0).astype("int8")

    df["pos_cash_active_flag"] = (status == "Active").astype("int8")
    df["pos_cash_completed_flag"] = (status == "Completed").astype("int8")
    df["pos_cash_demand_flag"] = (status == "Demand").astype("int8")
    df["pos_cash_signed_flag"] = (status == "Signed").astype("int8")
    df["pos_cash_status_xna_flag"] = (status == "XNA").astype("int8")

    agg = df.groupby("SK_ID_CURR").agg(
        pos_cash_months_observed=("MONTHS_BALANCE", "count"),
        pos_cash_contract_count=("SK_ID_PREV", "nunique"),
        pos_cash_avg_installment_count=("CNT_INSTALMENT", "mean"),
        pos_cash_avg_future_installment_count=("CNT_INSTALMENT_FUTURE", "mean"),
        pos_cash_min_future_installment_count=("CNT_INSTALMENT_FUTURE", "min"),
        pos_cash_max_future_installment_count=("CNT_INSTALMENT_FUTURE", "max"),
        pos_cash_dpd_count=("pos_cash_dpd_flag", "sum"),
        pos_cash_avg_dpd=("SK_DPD", "mean"),
        pos_cash_max_dpd=("SK_DPD", "max"),
        pos_cash_def_dpd_count=("pos_cash_def_dpd_flag", "sum"),
        pos_cash_avg_def_dpd=("SK_DPD_DEF", "mean"),
        pos_cash_max_def_dpd=("SK_DPD_DEF", "max"),
        pos_cash_active_count=("pos_cash_active_flag", "sum"),
        pos_cash_completed_count=("pos_cash_completed_flag", "sum"),
        pos_cash_demand_count=("pos_cash_demand_flag", "sum"),
        pos_cash_signed_count=("pos_cash_signed_flag", "sum"),
        pos_cash_status_xna_count=("pos_cash_status_xna_flag", "sum"),
    ).reset_index()

    agg["pos_cash_dpd_ratio"] = safe_divide(
        agg["pos_cash_dpd_count"],
        agg["pos_cash_months_observed"],
    )

    agg["pos_cash_def_dpd_ratio"] = safe_divide(
        agg["pos_cash_def_dpd_count"],
        agg["pos_cash_months_observed"],
    )

    agg["has_pos_cash_history"] = 1

    zero_fill_cols = [
        "pos_cash_months_observed",
        "pos_cash_contract_count",
        "pos_cash_dpd_count",
        "pos_cash_def_dpd_count",
        "pos_cash_active_count",
        "pos_cash_completed_count",
        "pos_cash_demand_count",
        "pos_cash_signed_count",
        "pos_cash_status_xna_count",
    ]

    return merge_to_base_customers(
        base_customers,
        agg,
        history_col="has_pos_cash_history",
        zero_fill_cols=zero_fill_cols,
    )


def build_credit_card_features(base_customers: pd.DataFrame) -> pd.DataFrame:
    print("[Batch B] Building credit_card_features.parquet ...")

    df = pd.read_csv(RAW_DIR / "credit_card_balance.csv")

    df["credit_card_utilization"] = safe_divide(
        df["AMT_BALANCE"],
        df["AMT_CREDIT_LIMIT_ACTUAL"],
    )

    df["credit_card_payment_to_min_ratio"] = safe_divide(
        df["AMT_PAYMENT_TOTAL_CURRENT"],
        df["AMT_INST_MIN_REGULARITY"],
    )

    df["credit_card_drawing_to_limit_ratio"] = safe_divide(
        df["AMT_DRAWINGS_CURRENT"],
        df["AMT_CREDIT_LIMIT_ACTUAL"],
    )

    status = df["NAME_CONTRACT_STATUS"].astype(str)

    df["credit_card_dpd_flag"] = (pd.to_numeric(df["SK_DPD"], errors="coerce") > 0).astype("int8")
    df["credit_card_def_dpd_flag"] = (pd.to_numeric(df["SK_DPD_DEF"], errors="coerce") > 0).astype("int8")

    df["credit_card_active_flag"] = (status == "Active").astype("int8")
    df["credit_card_completed_flag"] = (status == "Completed").astype("int8")
    df["credit_card_signed_flag"] = (status == "Signed").astype("int8")

    agg = df.groupby("SK_ID_CURR").agg(
        credit_card_months_observed=("MONTHS_BALANCE", "count"),
        credit_card_avg_balance=("AMT_BALANCE", "mean"),
        credit_card_max_balance=("AMT_BALANCE", "max"),
        credit_card_min_balance=("AMT_BALANCE", "min"),
        credit_card_avg_limit=("AMT_CREDIT_LIMIT_ACTUAL", "mean"),
        credit_card_max_limit=("AMT_CREDIT_LIMIT_ACTUAL", "max"),
        credit_card_avg_utilization=("credit_card_utilization", "mean"),
        credit_card_max_utilization=("credit_card_utilization", "max"),
        credit_card_avg_payment_to_min_ratio=("credit_card_payment_to_min_ratio", "mean"),
        credit_card_min_payment_to_min_ratio=("credit_card_payment_to_min_ratio", "min"),
        credit_card_total_drawings=("AMT_DRAWINGS_CURRENT", "sum"),
        credit_card_avg_drawings=("AMT_DRAWINGS_CURRENT", "mean"),
        credit_card_max_drawings=("AMT_DRAWINGS_CURRENT", "max"),
        credit_card_avg_drawing_to_limit_ratio=("credit_card_drawing_to_limit_ratio", "mean"),
        credit_card_max_drawing_to_limit_ratio=("credit_card_drawing_to_limit_ratio", "max"),
        credit_card_dpd_count=("credit_card_dpd_flag", "sum"),
        credit_card_avg_dpd=("SK_DPD", "mean"),
        credit_card_max_dpd=("SK_DPD", "max"),
        credit_card_def_dpd_count=("credit_card_def_dpd_flag", "sum"),
        credit_card_avg_def_dpd=("SK_DPD_DEF", "mean"),
        credit_card_max_def_dpd=("SK_DPD_DEF", "max"),
        credit_card_active_count=("credit_card_active_flag", "sum"),
        credit_card_completed_count=("credit_card_completed_flag", "sum"),
        credit_card_signed_count=("credit_card_signed_flag", "sum"),
    ).reset_index()

    agg["credit_card_dpd_ratio"] = safe_divide(
        agg["credit_card_dpd_count"],
        agg["credit_card_months_observed"],
    )

    agg["credit_card_def_dpd_ratio"] = safe_divide(
        agg["credit_card_def_dpd_count"],
        agg["credit_card_months_observed"],
    )

    agg["has_credit_card_history"] = 1

    zero_fill_cols = [
        "credit_card_months_observed",
        "credit_card_total_drawings",
        "credit_card_dpd_count",
        "credit_card_def_dpd_count",
        "credit_card_active_count",
        "credit_card_completed_count",
        "credit_card_signed_count",
    ]

    return merge_to_base_customers(
        base_customers,
        agg,
        history_col="has_credit_card_history",
        zero_fill_cols=zero_fill_cols,
    )


def write_feature_group_report(stats_list: list[dict]) -> None:
    report_path = REPORT_DIR / "feature_group_build_report.md"

    md = []
    md.append("# Feature Group Build Report\n")
    md.append(f"Created at: `{datetime.now().isoformat(timespec='seconds')}`\n")

    md.append("## Summary\n")
    md.append("| Feature group | Rows | Columns | Features | Duplicate SK_ID_CURR | Inf before clean | All-null features | Constant features | Status |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")

    for s in stats_list:
        md.append(
            f"| {s['group_name']} | {s['row_count']} | {s['column_count']} | "
            f"{s['feature_count_excluding_id']} | {s['duplicate_sk_id_curr']} | "
            f"{s['inf_count_before_cleaning']} | {s['all_null_feature_count']} | "
            f"{s['constant_feature_count']} | `{s['status']}` |"
        )

    md.append("\n## Output Files\n")
    for s in stats_list:
        md.append(f"- `{s['output_path']}` — {s['file_size_mb']} MB")

    md.append("\n## Validation Rules\n")
    md.append("- Each feature group must contain `SK_ID_CURR`.")
    md.append("- Each feature group must have at most one row per `SK_ID_CURR`.")
    md.append("- Feature outputs must not contain `TARGET`, `SK_ID_BUREAU`, or `SK_ID_PREV`.")
    md.append("- Feature outputs must not contain `inf` or `-inf`.")
    md.append("- Auxiliary feature groups include `has_*_history` indicators.")
    md.append("- Missing values are allowed at this stage; imputation happens after train/valid/test split.")

    blocked = [s for s in stats_list if s["status"] != "passed"]
    if blocked:
        md.append("\n## Blocking Errors\n")
        for s in blocked:
            md.append(f"### {s['group_name']}")
            for err in s["errors"]:
                md.append(f"- {err}")

    md.append("\n## Notes for Next Stage\n")
    md.append(
        "Batch C can merge these feature groups by `SK_ID_CURR` to build the unified feature matrix. "
        "No preprocessing, scaling, encoding, or model training has been performed in Batch B."
    )

    report_path.write_text("\n".join(md), encoding="utf-8")


def write_batch_b_summary(stats_list: list[dict]) -> None:
    all_passed = all(s["status"] == "passed" for s in stats_list)

    completed_before = 5
    batch_b_steps = 8
    completed = completed_before + (batch_b_steps if all_passed else 0)
    total = 20
    remaining = total - completed

    summary = {
        "batch_name": "batch_b_feature_engineering_layer",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "assumption": "Batch A Raw Audit Layer was already completed.",
        "pipeline_group": "Batch B - Feature Engineering Layer",
        "pipeline_group_status": "feature_engineering_layer_completed" if all_passed else "blocked",
        "technical_steps_completed": completed,
        "technical_steps_total": total,
        "technical_steps_remaining": remaining,
        "outputs": [s["output_path"] for s in stats_list],
        "feature_group_statuses": stats_list,
        "next_group": "Batch C - Feature Matrix + Registry Layer" if all_passed else None,
    }

    json_path = MANIFEST_DIR / "batch_b_feature_engineering_summary.json"
    json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    md = []
    md.append("# Batch B Summary — Feature Engineering Layer\n")
    md.append("Assumption: Batch A Raw Audit Layer was already completed.\n")
    md.append("## Batch Status\n")
    md.append(f"- Status: `{'feature_engineering_layer_completed' if all_passed else 'blocked'}`")
    md.append(f"- Technical steps completed: `{completed}/{total}`")
    md.append(f"- Technical steps remaining: `{remaining}/{total}`")

    if all_passed:
        md.append("- Next group: `Batch C - Feature Matrix + Registry Layer`")
    else:
        md.append("- Next group: blocked until errors are fixed")

    md.append("\n## Feature Groups\n")
    md.append("| Feature group | Output | Status |")
    md.append("|---|---|---|")

    for s in stats_list:
        md.append(f"| {s['group_name']} | `{s['output_path']}` | `{s['status']}` |")

    md.append("\n## Meaning for Next Stage\n")
    md.append(
        "The generated interim parquet files are customer-level feature groups. "
        "They are ready to be merged by `SK_ID_CURR` in Batch C if all statuses are `passed`."
    )

    md_path = REPORT_DIR / "batch_b_feature_engineering_summary.md"
    md_path.write_text("\n".join(md), encoding="utf-8")


def run_feature_builder(
    group_name: str,
    output_filename: str,
    builder: Callable[[pd.DataFrame], pd.DataFrame],
    base_customers: pd.DataFrame,
    expected_rows: int,
) -> dict:
    df = builder(base_customers)

    stats = save_feature_group(
        df=df,
        output_filename=output_filename,
        group_name=group_name,
    )

    if stats["row_count"] != expected_rows:
        stats["status"] = "blocked"
        stats["errors"].append(
            f"Row count mismatch: expected {expected_rows}, got {stats['row_count']}"
        )

    print(
        f"[Batch B] {group_name}: {stats['status']} "
        f"rows={stats['row_count']} cols={stats['column_count']} "
        f"output={stats['output_path']}"
    )

    del df
    gc.collect()

    return stats


def main() -> None:
    print("=== Batch B: Feature Engineering Layer ===")
    print("This batch creates customer-level feature groups.")
    print("No preprocessing, model training, SHAP, or LLM explanation is performed.\n")

    ensure_raw_files_exist()

    base_customers = load_base_customers()
    expected_rows = len(base_customers)

    print(f"[Batch B] Base customers from application_train: {expected_rows}")

    builders = [
        ("application_features", "application_features.parquet", build_application_features),
        ("bureau_features", "bureau_features.parquet", build_bureau_features),
        ("bureau_balance_features", "bureau_balance_features.parquet", build_bureau_balance_features),
        ("previous_application_features", "previous_application_features.parquet", build_previous_application_features),
        ("installments_features", "installments_features.parquet", build_installments_features),
        ("pos_cash_features", "pos_cash_features.parquet", build_pos_cash_features),
        ("credit_card_features", "credit_card_features.parquet", build_credit_card_features),
    ]

    stats_list = []

    for group_name, output_filename, builder in builders:
        stats = run_feature_builder(
            group_name=group_name,
            output_filename=output_filename,
            builder=builder,
            base_customers=base_customers,
            expected_rows=expected_rows,
        )
        stats_list.append(stats)

    write_feature_group_report(stats_list)
    write_batch_b_summary(stats_list)

    all_passed = all(s["status"] == "passed" for s in stats_list)

    print("\n=== Batch B completed ===")
    print("Produced files:")
    print("- data/interim/application_features.parquet")
    print("- data/interim/bureau_features.parquet")
    print("- data/interim/bureau_balance_features.parquet")
    print("- data/interim/previous_application_features.parquet")
    print("- data/interim/installments_features.parquet")
    print("- data/interim/pos_cash_features.parquet")
    print("- data/interim/credit_card_features.parquet")
    print("- data/reports/feature_group_build_report.md")
    print("- data/reports/batch_b_feature_engineering_summary.md")
    print("- data/manifests/batch_b_feature_engineering_summary.json")

    if all_passed:
        print("\nBatch B status: feature_engineering_layer_completed")
        print("Next: Batch C - Feature Matrix + Registry Layer")
    else:
        print("\nBatch B status: blocked")
        print("Check data/reports/feature_group_build_report.md for errors.")


if __name__ == "__main__":
    main()