# Batch E Summary — Preprocessing Layer

Assumption: Batch A, Batch B, Batch C, and Batch D were already completed.

## Batch Status

- Status: `preprocessing_layer_completed`
- Technical steps completed: `19/20`
- Technical steps remaining: `1/20`
- Next group: `Batch F - Model Training Layer`

## Feature Groups

- Numeric features: `152`
- Binary features: `7`
- Categorical features: `7`

## Target Splits

- Train positive rate: `0.080727`
- Valid positive rate: `0.080734`
- Test positive rate: `0.080734`

## Tree Model-Ready Dataset

- Status: `passed`
- Train shape: `[215257, 213]`
- Valid shape: `[46127, 213]`
- Test shape: `[46127, 213]`
- Feature count: `213`
- Missing counts: train=`0`, valid=`0`, test=`0`
- Inf counts: train=`0`, valid=`0`, test=`0`

## Linear Model-Ready Dataset

- Status: `passed`
- Train shape: `[215257, 213]`
- Valid shape: `[46127, 213]`
- Test shape: `[46127, 213]`
- Feature count: `213`
- Missing counts: train=`0`, valid=`0`, test=`0`
- Inf counts: train=`0`, valid=`0`, test=`0`

## Output Files

- `X_train_tree`: `data/processed/model_ready/tree/X_train_tree.parquet`
- `X_valid_tree`: `data/processed/model_ready/tree/X_valid_tree.parquet`
- `X_test_tree`: `data/processed/model_ready/tree/X_test_tree.parquet`
- `y_train_tree`: `data/processed/model_ready/tree/y_train.parquet`
- `y_valid_tree`: `data/processed/model_ready/tree/y_valid.parquet`
- `y_test_tree`: `data/processed/model_ready/tree/y_test.parquet`
- `X_train_linear`: `data/processed/model_ready/linear/X_train_linear.parquet`
- `X_valid_linear`: `data/processed/model_ready/linear/X_valid_linear.parquet`
- `X_test_linear`: `data/processed/model_ready/linear/X_test_linear.parquet`
- `y_train_linear`: `data/processed/model_ready/linear/y_train.parquet`
- `y_valid_linear`: `data/processed/model_ready/linear/y_valid.parquet`
- `y_test_linear`: `data/processed/model_ready/linear/y_test.parquet`
- `tree_preprocessor`: `artifacts/preprocessing/tree_preprocessor.joblib`
- `linear_preprocessor`: `artifacts/preprocessing/linear_preprocessor.joblib`
- `preprocessed_feature_columns_tree`: `ml/registry/preprocessed_feature_columns_tree.json`
- `preprocessed_feature_columns_linear`: `ml/registry/preprocessed_feature_columns_linear.json`
- `preprocessed_feature_mapping_tree`: `ml/registry/preprocessed_feature_mapping_tree.json`
- `preprocessed_feature_mapping_linear`: `ml/registry/preprocessed_feature_mapping_linear.json`
- `preprocessing_report`: `data/reports/preprocessing_report.md`
- `preprocessing_manifest`: `data/manifests/preprocessing_manifest.json`
- `batch_e_summary_report`: `data/reports/batch_e_preprocessing_summary.md`
- `batch_e_summary_manifest`: `data/manifests/batch_e_preprocessing_summary.json`