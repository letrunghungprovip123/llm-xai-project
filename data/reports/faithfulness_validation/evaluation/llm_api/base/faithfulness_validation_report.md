# Batch J.2 Faithfulness Validation Report

Created at: 2026-07-07T03:14:28.997Z
Status: **PASS_WITH_WARN**

## Inputs

- Claim extractions: `data/reports/faithfulness_validation/evaluation/llm_api/base/claim_extractions.jsonl`
- Explanation IR: `data/reports/explanation_ir/evaluation/explanation_ir.jsonl`

## Summary

- Validated records: 5
- PASS records: 0
- PASS_WITH_WARN records: 5
- FAIL records: 0
- Total claims: 47
- PASS claims: 31
- WARN claims: 16
- FAIL claims: 0

## Join Quality

- Joined records: 5
- Missing IR records: 0

## Per-record Results

| # | Status | IR ID | Explanation ID | Claims | Pass | Warn | Fail |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | PASS_WITH_WARN | `ir_xai_hist_gradient_boosting_v1_156227_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_156227_top_high_risk_156227` | 10 | 5 | 5 | 0 |
| 2 | PASS_WITH_WARN | `ir_xai_hist_gradient_boosting_v1_199300_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_199300_top_high_risk_199300` | 9 | 7 | 2 | 0 |
| 3 | PASS_WITH_WARN | `ir_xai_hist_gradient_boosting_v1_232843_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_232843_top_high_risk_232843` | 11 | 6 | 5 | 0 |
| 4 | PASS_WITH_WARN | `ir_xai_hist_gradient_boosting_v1_360304_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_360304_top_high_risk_360304` | 9 | 7 | 2 | 0 |
| 5 | PASS_WITH_WARN | `ir_xai_hist_gradient_boosting_v1_163956_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_163956_top_high_risk_163956` | 8 | 6 | 2 | 0 |

## Validator

- Version: `batch_j2_faithfulness_validator_v1.1`
- Mode: `rule_based_ir_faithfulness`
- LLM-as-judge: `false`
