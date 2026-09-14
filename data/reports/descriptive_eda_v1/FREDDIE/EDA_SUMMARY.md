# FREDDIE — Descriptive EDA v1

## Scope

- Descriptive characterization only.
- Uses frozen canonical train/validation/test splits.
- Does not refit preprocessing or predictive models.
- Does not alter targets, XAI, LLM generations, or certified results.

## Training population

- Rows: 725,468
- Predictors: 19
- Positive cases: 3,900
- Negative cases: 721,568
- Positive prevalence: 0.00537584
- Numeric/binary dtype predictors: 11
- Categorical predictors: 8

## Top missing numeric features

- classic_fico: 0.0336%
- original_dti: 0.0011%
- first_time_homebuyer_indicator: 0.0000%
- mortgage_insurance_percentage: 0.0000%
- original_cltv: 0.0000%
- original_upb: 0.0000%
- original_ltv: 0.0000%
- original_interest_rate: 0.0000%
- original_loan_term: 0.0000%
- number_of_borrowers: 0.0000%

## Most skewed numeric features

- super_conforming_flag: skew=8.992338 (right_skewed)
- original_loan_term: skew=-3.603485 (left_skewed)
- original_ltv: skew=-1.036123 (left_skewed)
- original_cltv: skew=-1.015605 (left_skewed)
- original_upb: skew=0.919767 (right_skewed)
- classic_fico: skew=-0.793398 (left_skewed)
- mortgage_insurance_percentage: skew=0.768117 (right_skewed)
- original_dti: skew=-0.721217 (left_skewed)
- number_of_borrowers: skew=0.575399 (right_skewed)
- first_time_homebuyer_indicator: skew=0.523719 (right_skewed)