# Batch J.2 Faithfulness Validation Report

Created at: 2026-07-06T03:16:12.453Z
Status: **FAIL**

## Inputs

- Claim extractions: `data/reports/faithfulness_validation/evaluation/llm_api/claim_extractions.jsonl`
- Explanation IR: `data/reports/explanation_ir/evaluation/explanation_ir.jsonl`

## Summary

- Validated records: 5
- PASS records: 0
- PASS_WITH_WARN records: 4
- FAIL records: 1
- Total claims: 49
- PASS claims: 15
- WARN claims: 33
- FAIL claims: 1

## Join Quality

- Joined records: 5
- Missing IR records: 0

## Per-record Results

| # | Status | IR ID | Explanation ID | Claims | Pass | Warn | Fail |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | PASS_WITH_WARN | `ir_xai_hist_gradient_boosting_v1_156227_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_156227_top_high_risk_156227` | 10 | 3 | 7 | 0 |
| 2 | PASS_WITH_WARN | `ir_xai_hist_gradient_boosting_v1_199300_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_199300_top_high_risk_199300` | 9 | 3 | 6 | 0 |
| 3 | PASS_WITH_WARN | `ir_xai_hist_gradient_boosting_v1_232843_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_232843_top_high_risk_232843` | 9 | 3 | 6 | 0 |
| 4 | PASS_WITH_WARN | `ir_xai_hist_gradient_boosting_v1_360304_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_360304_top_high_risk_360304` | 12 | 3 | 9 | 0 |
| 5 | FAIL | `ir_xai_hist_gradient_boosting_v1_163956_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_163956_top_high_risk_163956` | 9 | 3 | 5 | 1 |

## Validator

- Version: `batch_j2_faithfulness_validator_v1.0`
- Mode: `rule_based_ir_faithfulness`
- LLM-as-judge: `false`
