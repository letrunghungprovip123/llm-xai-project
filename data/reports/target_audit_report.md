# Target Audit Report

Created at: `2026-06-21T11:19:21`

## Target Summary

- Total rows: `307511`
- TARGET values found: `[0, 1]`
- TARGET missing count: `0`
- TARGET = 0 count: `282686`
- TARGET = 1 count: `24825`
- TARGET = 1 ratio: `0.080729`
- Duplicate SK_ID_CURR count: `0`
- Duplicate target per SK_ID_CURR: `0`

## Class Imbalance Assessment

This is a credit default risk problem, so class imbalance is expected. Model evaluation must not rely only on accuracy.

Assessment: `class_imbalance_expected_and_significant`

## Recommended Metrics for Model Stage

- ROC-AUC
- PR-AUC
- Recall
- Precision
- F1-score
- Confusion matrix
- Calibration if time allows

## Split Recommendation

- Use stratified train/validation/test split by `TARGET`.
- Split unit must be `SK_ID_CURR`.
- Preprocessing must be fitted only after the split, using training data only.

## Status

`target_audit_passed`
