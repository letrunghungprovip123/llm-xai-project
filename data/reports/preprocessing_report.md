# Preprocessing Report

Created at: `2026-06-22T11:31:50`

## Purpose

Batch E fits preprocessing only on the training split and transforms validation/test splits without refitting. It produces model-ready datasets for tree-based models and linear models.

## Input Validation

- Status: `passed`
- Train rows: `215257`
- Valid rows: `46127`
- Test rows: `46127`
- Model feature count: `166`
- ID columns: `['SK_ID_CURR']`
- Target column: `TARGET`
- Warning count: `0`
- Error count: `0`

## Target Validation

- Status: `passed`
- Train positive rate: `0.080727`
- Valid positive rate: `0.080734`
- Test positive rate: `0.080734`

## Feature Groups

- Numeric features: `152`
- Binary features: `7`
- Categorical features: `7`

### Categorical Features

- `NAME_CONTRACT_TYPE`
- `NAME_INCOME_TYPE`
- `NAME_EDUCATION_TYPE`
- `NAME_FAMILY_STATUS`
- `NAME_HOUSING_TYPE`
- `OCCUPATION_TYPE`
- `ORGANIZATION_TYPE`

### Binary Features

- `days_employed_abnormal`
- `has_bureau_history`
- `has_bureau_balance_history`
- `has_previous_application_history`
- `has_installment_history`
- `has_pos_cash_history`
- `has_credit_card_history`

## Tree Model-Ready Dataset

- Status: `passed`
- Train shape: `[215257, 213]`
- Valid shape: `[46127, 213]`
- Test shape: `[46127, 213]`
- Preprocessed feature count: `213`
- Train missing count: `0`
- Valid missing count: `0`
- Test missing count: `0`
- Train inf count: `0`
- Valid inf count: `0`
- Test inf count: `0`

## Linear Model-Ready Dataset

- Status: `passed`
- Train shape: `[215257, 213]`
- Valid shape: `[46127, 213]`
- Test shape: `[46127, 213]`
- Preprocessed feature count: `213`
- Train missing count: `0`
- Valid missing count: `0`
- Test missing count: `0`
- Train inf count: `0`
- Valid inf count: `0`
- Test inf count: `0`

## Preprocessing Strategy

- Numeric features for tree models: `SimpleImputer(strategy='median')`
- Numeric features for linear models: `SimpleImputer(strategy='median') + StandardScaler`
- Binary features: `SimpleImputer(strategy='most_frequent')`
- Categorical missing token: `__MISSING__`
- Rare category token: `__RARE__`
- Unknown category token: `__UNKNOWN__`
- Rare category threshold: `0.01`
- Categorical encoding: `OneHotEncoder(handle_unknown='ignore')`
- Preprocessing fit: `train only`
- Validation/test transform: `using train-fitted artifacts only`

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

## Artifact and Registry Files

- `tree_preprocessor`: `artifacts/preprocessing/tree_preprocessor.joblib`
- `linear_preprocessor`: `artifacts/preprocessing/linear_preprocessor.joblib`
- `preprocessed_feature_columns_tree`: `ml/registry/preprocessed_feature_columns_tree.json`
- `preprocessed_feature_columns_linear`: `ml/registry/preprocessed_feature_columns_linear.json`
- `preprocessed_feature_mapping_tree`: `ml/registry/preprocessed_feature_mapping_tree.json`
- `preprocessed_feature_mapping_linear`: `ml/registry/preprocessed_feature_mapping_linear.json`