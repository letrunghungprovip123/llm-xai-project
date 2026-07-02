# Split Report

Created at: `2026-06-22T10:32:35`

## Split Configuration

- Split strategy: `stratified_by_TARGET`
- Split unit: `SK_ID_CURR`
- Random state: `42`
- Train ratio: `0.7`
- Valid ratio: `0.15`
- Test ratio: `0.15`
- Full rows: `307511`
- Split row total: `307511`
- Full positive rate: `0.080729`

## Split Summary

| Split | Rows | Positive | Negative | Positive rate | Gap from full |
|---|---:|---:|---:|---:|---:|
| train | 215257 | 17377 | 197880 | 0.080727 | 0.000002 |
| valid | 46127 | 3724 | 42403 | 0.080734 | 0.000005 |
| test | 46127 | 3724 | 42403 | 0.080734 | 0.000005 |

## ID Overlap Check

- Train/valid overlap: `0`
- Train/test overlap: `0`
- Valid/test overlap: `0`
- Split status: `passed`

## Output Files

- `X_train`: `data/processed/splits/X_train.parquet`
- `y_train`: `data/processed/splits/y_train.parquet`
- `X_valid`: `data/processed/splits/X_valid.parquet`
- `y_valid`: `data/processed/splits/y_valid.parquet`
- `X_test`: `data/processed/splits/X_test.parquet`
- `y_test`: `data/processed/splits/y_test.parquet`
- `model_feature_columns`: `ml/registry/model_feature_columns.json`
- `id_columns`: `ml/registry/id_columns.json`
- `target_column`: `ml/registry/target_column.json`
- `model_feature_metadata`: `ml/registry/model_feature_metadata.json`