# Missing Value and Anomaly Audit Report

Created at: `2026-06-21T11:20:26`

## Summary

- Tables audited: `7`
- Columns profiled for missing values: `218`
- Columns profiled for anomalies: `218`
- High missing columns >= 40%: `62`
- High-cardinality categorical columns: `1`
- Columns with special anomaly violations: `13`
- Columns with infinite values: `0`

## High Missing Columns

| Table | Column | Missing % |
|---|---|---:|
| previous_application.csv | RATE_INTEREST_PRIVILEGED | 99.6437 |
| previous_application.csv | RATE_INTEREST_PRIMARY | 99.6437 |
| bureau.csv | AMT_ANNUITY | 71.4735 |
| application_train.csv | COMMONAREA_MEDI | 69.8723 |
| application_train.csv | COMMONAREA_AVG | 69.8723 |
| application_train.csv | COMMONAREA_MODE | 69.8723 |
| application_train.csv | NONLIVINGAPARTMENTS_MEDI | 69.433 |
| application_train.csv | NONLIVINGAPARTMENTS_MODE | 69.433 |
| application_train.csv | NONLIVINGAPARTMENTS_AVG | 69.433 |
| application_train.csv | FONDKAPREMONT_MODE | 68.3862 |
| application_train.csv | LIVINGAPARTMENTS_MEDI | 68.355 |
| application_train.csv | LIVINGAPARTMENTS_AVG | 68.355 |
| application_train.csv | LIVINGAPARTMENTS_MODE | 68.355 |
| application_train.csv | FLOORSMIN_MODE | 67.8486 |
| application_train.csv | FLOORSMIN_AVG | 67.8486 |
| application_train.csv | FLOORSMIN_MEDI | 67.8486 |
| application_train.csv | YEARS_BUILD_MODE | 66.4978 |
| application_train.csv | YEARS_BUILD_AVG | 66.4978 |
| application_train.csv | YEARS_BUILD_MEDI | 66.4978 |
| application_train.csv | OWN_CAR_AGE | 65.9908 |
| bureau.csv | AMT_CREDIT_MAX_OVERDUE | 65.5133 |
| application_train.csv | LANDAREA_MEDI | 59.3767 |
| application_train.csv | LANDAREA_AVG | 59.3767 |
| application_train.csv | LANDAREA_MODE | 59.3767 |
| application_train.csv | BASEMENTAREA_MEDI | 58.516 |
| application_train.csv | BASEMENTAREA_MODE | 58.516 |
| application_train.csv | BASEMENTAREA_AVG | 58.516 |
| application_train.csv | EXT_SOURCE_1 | 56.3811 |
| application_train.csv | NONLIVINGAREA_MEDI | 55.1792 |
| application_train.csv | NONLIVINGAREA_AVG | 55.1792 |
| application_train.csv | NONLIVINGAREA_MODE | 55.1792 |
| previous_application.csv | AMT_DOWN_PAYMENT | 53.6365 |
| previous_application.csv | RATE_DOWN_PAYMENT | 53.6365 |
| application_train.csv | ELEVATORS_MEDI | 53.296 |
| application_train.csv | ELEVATORS_AVG | 53.296 |
| application_train.csv | ELEVATORS_MODE | 53.296 |
| application_train.csv | WALLSMATERIAL_MODE | 50.8408 |
| application_train.csv | APARTMENTS_AVG | 50.7497 |
| application_train.csv | APARTMENTS_MEDI | 50.7497 |
| application_train.csv | APARTMENTS_MODE | 50.7497 |
| application_train.csv | ENTRANCES_MODE | 50.3488 |
| application_train.csv | ENTRANCES_AVG | 50.3488 |
| application_train.csv | ENTRANCES_MEDI | 50.3488 |
| application_train.csv | LIVINGAREA_AVG | 50.1933 |
| application_train.csv | LIVINGAREA_MEDI | 50.1933 |
| application_train.csv | LIVINGAREA_MODE | 50.1933 |
| application_train.csv | HOUSETYPE_MODE | 50.1761 |
| application_train.csv | FLOORSMAX_MODE | 49.7608 |
| application_train.csv | FLOORSMAX_AVG | 49.7608 |
| application_train.csv | FLOORSMAX_MEDI | 49.7608 |

## High-cardinality Categorical Columns

| Table | Column | Unique count | Rare category count below 1% |
|---|---|---:|---:|
| application_train.csv | ORGANIZATION_TYPE | 58.0 | 41.0 |

## Special Anomaly Violations

| Table | Column | Rule | Violation count |
|---|---|---|---:|
| credit_card_balance.csv | AMT_INST_MIN_REGULARITY | <=0 | 1928864 |
| credit_card_balance.csv | AMT_CREDIT_LIMIT_ACTUAL | <=0 | 753823 |
| previous_application.csv | AMT_APPLICATION | <=0 | 392402 |
| previous_application.csv | AMT_CREDIT | <=0 | 336768 |
| bureau.csv | AMT_CREDIT_SUM | <=0 | 66582 |
| application_train.csv | DAYS_EMPLOYED | abnormal_days_employed | 55376 |
| bureau.csv | AMT_CREDIT_SUM_DEBT | <0 | 8418 |
| previous_application.csv | AMT_GOODS_PRICE | <=0 | 6869 |
| credit_card_balance.csv | AMT_BALANCE | <0 | 2345 |
| previous_application.csv | AMT_ANNUITY | <=0 | 1637 |
| bureau.csv | AMT_CREDIT_SUM_LIMIT | <0 | 351 |
| installments_payments.csv | AMT_INSTALMENT | <=0 | 290 |
| credit_card_balance.csv | AMT_DRAWINGS_CURRENT | <0 | 3 |

## Infinite Value Check

No infinite values detected in raw numeric columns.

## Important Notes for Next Stage

- Missing values are not imputed in this audit stage.
- Numeric values are not scaled or standardized in this audit stage.
- Ratio features must use safe division in the feature engineering stage.
- `DAYS_EMPLOYED` abnormal sentinel values must be handled before deriving `employment_years`.
- Any `inf` or `-inf` values produced later must be converted to `NaN` before preprocessing.
- Preprocessing must be fitted only after train/valid/test split.

## Status

`missing_anomaly_audit_passed`
