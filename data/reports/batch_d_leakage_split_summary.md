# Batch D Summary — Leakage + Split Layer

Assumption: Batch A, Batch B, and Batch C were already completed.

## Batch Status

- Status: `leakage_split_layer_completed`
- Technical steps completed: `18/20`
- Technical steps remaining: `2/20`
- Next group: `Batch E - Preprocessing Layer`

## Leakage Audit

- Status: `passed`
- Warning count: `1`
- Error count: `0`

## Split Summary

- Status: `passed`
- Strategy: `stratified_by_TARGET`
- Split unit: `SK_ID_CURR`
- Random state: `42`
- Full rows: `307511`
- Split row total: `307511`
- Full positive rate: `0.080729`

| Split | Rows | Positive rate |
|---|---:|---:|
| train | 215257 | 0.080727 |
| valid | 46127 | 0.080734 |
| test | 46127 | 0.080734 |

## Model Feature Metadata

- Model feature count: `166`
- ID columns: `['SK_ID_CURR']`
- Target column: `TARGET`
- Excluded columns: `['SK_ID_CURR']`
- allowed_for_model=False excluded: `[]`

## ID Overlap Check

- Train/valid overlap: `0`
- Train/test overlap: `0`
- Valid/test overlap: `0`

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
- `leakage_audit_report`: `data/reports/leakage_audit_report.md`
- `split_report`: `data/reports/split_report.md`
- `split_manifest`: `data/manifests/split_manifest.json`
- `batch_d_summary_report`: `data/reports/batch_d_leakage_split_summary.md`
- `batch_d_summary_manifest`: `data/manifests/batch_d_leakage_split_summary.json`

## Warnings

- Leakage: suspicious feature names found: 3