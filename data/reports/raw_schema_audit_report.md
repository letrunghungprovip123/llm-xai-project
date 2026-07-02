# Raw Schema Audit Report

Created at: `2026-06-21T11:03:59`

## application_train.csv

- Rows: `307511`
- Columns: `122`
- Duplicate rows estimated by hash: `0`
- File size MB: `158.44`
- Expected keys: `['SK_ID_CURR', 'TARGET']`
- Missing keys: `[]`

## bureau.csv

- Rows: `1716428`
- Columns: `17`
- Duplicate rows estimated by hash: `0`
- File size MB: `162.14`
- Expected keys: `['SK_ID_CURR', 'SK_ID_BUREAU']`
- Missing keys: `[]`

## bureau_balance.csv

- Rows: `27299925`
- Columns: `3`
- Duplicate rows estimated by hash: `0`
- File size MB: `358.19`
- Expected keys: `['SK_ID_BUREAU']`
- Missing keys: `[]`

## previous_application.csv

- Rows: `1670214`
- Columns: `37`
- Duplicate rows estimated by hash: `0`
- File size MB: `386.21`
- Expected keys: `['SK_ID_CURR', 'SK_ID_PREV']`
- Missing keys: `[]`

## installments_payments.csv

- Rows: `13605401`
- Columns: `8`
- Duplicate rows estimated by hash: `0`
- File size MB: `689.62`
- Expected keys: `['SK_ID_CURR', 'SK_ID_PREV']`
- Missing keys: `[]`

## POS_CASH_balance.csv

- Rows: `10001358`
- Columns: `8`
- Duplicate rows estimated by hash: `0`
- File size MB: `374.51`
- Expected keys: `['SK_ID_CURR', 'SK_ID_PREV']`
- Missing keys: `[]`

## credit_card_balance.csv

- Rows: `3840312`
- Columns: `23`
- Duplicate rows estimated by hash: `0`
- File size MB: `404.91`
- Expected keys: `['SK_ID_CURR', 'SK_ID_PREV']`
- Missing keys: `[]`

## Notes

- Missing percentage, dtype, unique values, and sample values are saved in `raw_schema_summary.csv`.
- Raw files were only read, not modified.