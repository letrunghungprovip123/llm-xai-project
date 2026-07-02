# Leakage Audit Report

Created at: `2026-06-22T10:32:35`

## Overall Status

- Status: `passed`
- Error count: `0`
- Warning count: `1`

## X/y Alignment Check

- X rows: `307511`
- y rows: `307511`
- Duplicate SK_ID_CURR in X: `0`
- Duplicate SK_ID_CURR in y: `0`
- IDs in X but not y: `0`
- IDs in y but not X: `0`
- Missing TARGET after merge: `0`
- TARGET values: `[0, 1]`
- TARGET positive rate: `0.08072881945686496`
- Status: `passed`

## Target and ID Leakage Check

- Forbidden columns found: `[]`
- Inf/-inf count: `0`
- Suspicious name feature count: `3`
- Status: `passed`

### Suspicious Feature Name Examples

- `pos_cash_avg_future_installment_count` matched `['future']`
- `pos_cash_min_future_installment_count` matched `['future']`
- `pos_cash_max_future_installment_count` matched `['future']`

## Registry Consistency Check

- Feature count in matrix: `166`
- Registry entry count: `166`
- Missing registry entries: `0`
- Extra registry entries: `0`
- Unknown concept count: `0`
- allowed_for_model=False count: `0`
- Sensitive feature count: `15`
- Explanation-limited feature count: `15`
- Status: `passed`

## Correlation Warning Check

- Numeric features checked: `159`
- Warning threshold: `abs(correlation) >= 0.8`
- Suspicious correlation count: `0`
- Status: `passed`

### Top Numeric Correlations with TARGET

| Feature | Correlation | Abs correlation |
|---|---:|---:|
| `ext_source_mean` | `-0.222052` | `0.222052` |
| `ext_source_max` | `-0.196876` | `0.196876` |
| `ext_source_min` | `-0.185266` | `0.185266` |
| `EXT_SOURCE_3` | `-0.178919` | `0.178919` |
| `EXT_SOURCE_2` | `-0.160472` | `0.160472` |
| `EXT_SOURCE_1` | `-0.155317` | `0.155317` |
| `credit_card_avg_utilization` | `0.135560` | `0.135560` |
| `credit_card_avg_drawing_to_limit_ratio` | `0.098962` | `0.098962` |
| `credit_card_max_utilization` | `0.097011` | `0.097011` |
| `bureau_avg_days_credit` | `0.089729` | `0.089729` |
| `credit_card_avg_balance` | `0.087177` | `0.087177` |
| `installment_recent_late_payment_ratio` | `0.080807` | `0.080807` |
| `installment_recent_late_payment_count` | `0.079100` | `0.079100` |
| `age_years` | `-0.078239` | `0.078239` |
| `previous_refusal_ratio` | `0.077671` | `0.077671` |
| `credit_card_max_drawing_to_limit_ratio` | `0.075688` | `0.075688` |
| `bureau_min_days_credit` | `0.075248` | `0.075248` |
| `bureau_long_history_months` | `-0.075248` | `0.075248` |
| `employment_years` | `-0.074948` | `0.074948` |
| `installment_late_payment_ratio` | `0.070015` | `0.070015` |
| `bureau_recent_loan_count` | `0.069967` | `0.069967` |
| `credit_to_goods_price_ratio` | `0.069427` | `0.069427` |
| `credit_card_max_balance` | `0.068798` | `0.068798` |
| `installment_recent_underpayment_ratio` | `0.068700` | `0.068700` |
| `installment_recent_underpayment_count` | `0.067356` | `0.067356` |
| `previous_refused_count` | `0.064756` | `0.064756` |
| `credit_card_min_balance` | `0.064163` | `0.064163` |
| `previous_approval_ratio` | `-0.063521` | `0.063521` |
| `installment_underpayment_ratio` | `0.062612` | `0.062612` |
| `bureau_debt_to_credit_ratio` | `0.060235` | `0.060235` |

## Warnings

- suspicious feature names found: 3