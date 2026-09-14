# HOME_CREDIT — Descriptive EDA v1

## Scope

- Descriptive characterization only.
- Uses frozen canonical train/validation/test splits.
- Does not refit preprocessing or predictive models.
- Does not alter targets, XAI, LLM generations, or certified results.

## Training population

- Rows: 215,257
- Predictors: 166
- Positive cases: 17,377
- Negative cases: 197,880
- Positive prevalence: 0.08072676
- Numeric/binary dtype predictors: 159
- Categorical predictors: 7

## Top missing numeric features

- credit_card_min_payment_to_min_ratio: 80.6455%
- credit_card_avg_payment_to_min_ratio: 80.6455%
- credit_card_max_drawing_to_limit_ratio: 71.9034%
- credit_card_avg_drawing_to_limit_ratio: 71.9034%
- credit_card_max_utilization: 71.9034%
- credit_card_avg_utilization: 71.9034%
- credit_card_min_balance: 71.6158%
- credit_card_max_dpd: 71.6158%
- credit_card_avg_dpd: 71.6158%
- credit_card_max_drawings: 71.6158%

## Most skewed numeric features

- pos_cash_status_xna_count: skew=463.957972 (right_skewed)
- AMT_INCOME_TOTAL: skew=360.911898 (right_skewed)
- installment_recent_payment_ratio_avg: skew=273.372628 (right_skewed)
- bureau_debt_to_credit_ratio: skew=-231.084476 (left_skewed)
- credit_card_min_payment_to_min_ratio: skew=203.357311 (right_skewed)
- credit_card_avg_payment_to_min_ratio: skew=202.622564 (right_skewed)
- income_per_family_member: skew=201.385810 (right_skewed)
- installment_payment_ratio_avg: skew=177.767000 (right_skewed)
- installment_payment_ratio_max: skew=164.275263 (right_skewed)
- bureau_overdue_amount_max: skew=162.601237 (right_skewed)