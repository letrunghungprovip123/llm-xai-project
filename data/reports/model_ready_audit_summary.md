# Final Model-Ready Data Audit Summary

Created at: `2026-06-22T12:35:45`

## Status

- Status: `passed`
- Error count: `0`
- Warning count: `1`
- Features with warning flags: `1045`
- High PSI feature rows: `0`

## What This Audit Covers

- Dataset-level model-ready validation
- Per-feature numeric descriptive statistics
- Mean, median, standard deviation, variance, min/max
- Quantiles: p1, p5, p10, p25, p50, p75, p90, p95, p99
- IQR outlier audit
- Z-score outlier audit
- Skewness and skew direction
- Kurtosis
- Zero/negative/positive value rates
- Target correlation and target-wise mean/median differences
- Train vs valid/test PSI drift audit
- One-hot encoded feature mapping
- Concept-level summary

## Output CSV Files

- `dataset_level_audit`: `data/reports/model_ready_audit/dataset_level_audit.csv`
- `tree_feature_numeric_audit`: `data/reports/model_ready_audit/tree_feature_numeric_audit.csv`
- `linear_feature_numeric_audit`: `data/reports/model_ready_audit/linear_feature_numeric_audit.csv`
- `feature_warning_flags`: `data/reports/model_ready_audit/feature_warning_flags.csv`
- `split_drift_psi_audit`: `data/reports/model_ready_audit/split_drift_psi_audit.csv`
- `one_hot_feature_audit`: `data/reports/model_ready_audit/one_hot_feature_audit.csv`
- `concept_level_audit`: `data/reports/model_ready_audit/concept_level_audit.csv`

## Warnings

- Features with distribution warning flags: 1045