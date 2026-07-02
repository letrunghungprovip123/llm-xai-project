# Batch B Summary — Feature Engineering Layer

Assumption: Batch A Raw Audit Layer was already completed.

## Batch Status

- Status: `feature_engineering_layer_completed`
- Technical steps completed: `13/20`
- Technical steps remaining: `7/20`
- Next group: `Batch C - Feature Matrix + Registry Layer`

## Feature Groups

| Feature group | Output | Status |
|---|---|---|
| application_features | `data/interim/application_features.parquet` | `passed` |
| bureau_features | `data/interim/bureau_features.parquet` | `passed` |
| bureau_balance_features | `data/interim/bureau_balance_features.parquet` | `passed` |
| previous_application_features | `data/interim/previous_application_features.parquet` | `passed` |
| installments_features | `data/interim/installments_features.parquet` | `passed` |
| pos_cash_features | `data/interim/pos_cash_features.parquet` | `passed` |
| credit_card_features | `data/interim/credit_card_features.parquet` | `passed` |

## Meaning for Next Stage

The generated interim parquet files are customer-level feature groups. They are ready to be merged by `SK_ID_CURR` in Batch C if all statuses are `passed`.