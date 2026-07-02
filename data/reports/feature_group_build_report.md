# Feature Group Build Report

Created at: `2026-06-22T09:31:20`

## Summary

| Feature group | Rows | Columns | Features | Duplicate SK_ID_CURR | Inf before clean | All-null features | Constant features | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| application_features | 307511 | 33 | 32 | 0 | 0 | 0 | 0 | `passed` |
| bureau_features | 307511 | 27 | 26 | 0 | 0 | 0 | 0 | `passed` |
| bureau_balance_features | 307511 | 13 | 12 | 0 | 0 | 0 | 0 | `passed` |
| previous_application_features | 307511 | 23 | 22 | 0 | 0 | 0 | 0 | `passed` |
| installments_features | 307511 | 28 | 27 | 0 | 0 | 0 | 0 | `passed` |
| pos_cash_features | 307511 | 21 | 20 | 0 | 0 | 0 | 0 | `passed` |
| credit_card_features | 307511 | 28 | 27 | 0 | 0 | 0 | 0 | `passed` |

## Output Files

- `data/interim/application_features.parquet` — 22.48 MB
- `data/interim/bureau_features.parquet` — 16.31 MB
- `data/interim/bureau_balance_features.parquet` — 3.45 MB
- `data/interim/previous_application_features.parquet` — 17.85 MB
- `data/interim/installments_features.parquet` — 17.18 MB
- `data/interim/pos_cash_features.parquet` — 5.97 MB
- `data/interim/credit_card_features.parquet` — 8.73 MB

## Validation Rules

- Each feature group must contain `SK_ID_CURR`.
- Each feature group must have at most one row per `SK_ID_CURR`.
- Feature outputs must not contain `TARGET`, `SK_ID_BUREAU`, or `SK_ID_PREV`.
- Feature outputs must not contain `inf` or `-inf`.
- Auxiliary feature groups include `has_*_history` indicators.
- Missing values are allowed at this stage; imputation happens after train/valid/test split.

## Notes for Next Stage

Batch C can merge these feature groups by `SK_ID_CURR` to build the unified feature matrix. No preprocessing, scaling, encoding, or model training has been performed in Batch B.