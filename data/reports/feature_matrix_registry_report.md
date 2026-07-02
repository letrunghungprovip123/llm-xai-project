# Feature Matrix and Registry Report

Created at: `2026-06-22T10:14:10`

## Purpose

Batch C merges all Batch B customer-level feature groups into one official model feature matrix, separates the target, and builds concept/feature registries for later preprocessing, modeling, SHAP, and LLM explanation.

## Feature Group Merge Summary

| Feature group | Rows | Columns | Features | Duplicate SK_ID_CURR | Inf count | Status |
|---|---:|---:|---:|---:|---:|---|
| application_features | 307511 | 33 | 32 | 0 | 0 | `merged` |
| bureau_features | 307511 | 27 | 26 | 0 | 0 | `merged` |
| bureau_balance_features | 307511 | 13 | 12 | 0 | 0 | `merged` |
| previous_application_features | 307511 | 23 | 22 | 0 | 0 | `merged` |
| installments_features | 307511 | 28 | 27 | 0 | 0 | `merged` |
| pos_cash_features | 307511 | 21 | 20 | 0 | 0 | `merged` |
| credit_card_features | 307511 | 28 | 27 | 0 | 0 | `merged` |

## Final Feature Matrix

- Rows: `307511`
- Columns: `167`
- Model feature count excluding `SK_ID_CURR`: `166`
- Numeric features: `159`
- Categorical features: `7`
- Binary indicator features: `7`
- Duplicate `SK_ID_CURR`: `0`
- Forbidden columns found: `[]`
- Inf/-inf count: `0`
- All-null feature count: `0`
- Constant feature count: `0`
- Matrix status: `passed`

## Target File

- Rows: `307511`
- Columns: `2`
- Duplicate `SK_ID_CURR`: `0`
- Missing TARGET: `0`
- TARGET values: `[0, 1]`
- TARGET positive count: `24825`
- TARGET negative count: `282686`
- TARGET positive rate: `0.080729`
- Target status: `passed`

## Registry Validation

- Feature count: `166`
- Feature registry entries: `166`
- Missing feature registry entries: `0`
- Extra feature registry entries: `0`
- Concepts used: `['applicant_stability', 'application_profile', 'bureau_monthly_behavior', 'credit_card_usage_behavior', 'external_credit_history', 'external_score_signal', 'installment_repayment_behavior', 'loan_affordability', 'pos_cash_behavior', 'previous_application_behavior']`
- Missing concepts: `0`
- Features missing concept: `0`
- Explanation-blocked features: `0`
- Explanation-limited features: `15`
- Sensitive features: `15`
- Suspicious metadata count: `0`
- Registry status: `passed`

## Top Missing Features

| Feature | Missing rate |
|---|---:|
| `credit_card_avg_payment_to_min_ratio` | `0.807230` |
| `credit_card_min_payment_to_min_ratio` | `0.807230` |
| `credit_card_max_drawing_to_limit_ratio` | `0.720218` |
| `credit_card_max_utilization` | `0.720218` |
| `credit_card_avg_utilization` | `0.720218` |
| `credit_card_avg_drawing_to_limit_ratio` | `0.720218` |
| `credit_card_avg_dpd` | `0.717392` |
| `credit_card_max_drawings` | `0.717392` |
| `credit_card_avg_drawings` | `0.717392` |
| `credit_card_def_dpd_ratio` | `0.717392` |
| `credit_card_dpd_ratio` | `0.717392` |
| `credit_card_max_limit` | `0.717392` |
| `credit_card_avg_limit` | `0.717392` |
| `credit_card_max_dpd` | `0.717392` |
| `credit_card_min_balance` | `0.717392` |
| `credit_card_avg_balance` | `0.717392` |
| `credit_card_max_def_dpd` | `0.717392` |
| `credit_card_avg_def_dpd` | `0.717392` |
| `credit_card_max_balance` | `0.717392` |
| `bureau_balance_recent_bad_status_ratio` | `0.707149` |
| `bureau_balance_avg_status_numeric` | `0.705324` |
| `bureau_balance_max_status_numeric` | `0.705324` |
| `bureau_balance_bad_status_ratio` | `0.700073` |
| `EXT_SOURCE_1` | `0.563811` |
| `installment_max_days_late` | `0.495956` |
| `installment_avg_days_late` | `0.495956` |
| `OCCUPATION_TYPE` | `0.313455` |
| `bureau_credit_limit_mean` | `0.211599` |
| `EXT_SOURCE_3` | `0.198253` |
| `employment_years` | `0.180078` |

## Output Files

- `data/processed/feature_matrix_full.parquet`
- `data/processed/target_full.parquet`
- `ml/registry/concept_registry.yaml`
- `ml/registry/feature_registry.yaml`
- `ml/registry/feature_registry.csv`
- `data/reports/feature_matrix_registry_report.md`
- `data/reports/batch_c_feature_matrix_registry_summary.md`
- `data/manifests/batch_c_feature_matrix_registry_summary.json`

## Validation Rules

- `feature_matrix_full.parquet` must contain `SK_ID_CURR`.
- `feature_matrix_full.parquet` must not contain `TARGET`.
- `feature_matrix_full.parquet` must not contain `SK_ID_BUREAU` or `SK_ID_PREV`.
- `feature_matrix_full.parquet` must have exactly one row per `SK_ID_CURR`.
- `target_full.parquet` must contain only `SK_ID_CURR` and `TARGET`.
- No `inf` or `-inf` should remain in the feature matrix.
- Missing values are allowed at this stage; imputation happens after train/valid/test split.
- Categorical strings are allowed at this stage; encoding happens after train/valid/test split.
- Registry value_type/unit/formatting_rule are checked to avoid obvious metadata mistakes.

## Notes for Next Stage

Batch D can now perform leakage checks and train/validation/test split. No preprocessing, scaling, one-hot encoding, model training, SHAP, or LLM explanation has been performed in Batch C.