# Batch J.2 Faithfulness Validation Report

Created at: 2026-07-07T02:16:39.884Z
Status: **PASS_WITH_WARN**

## Inputs

- Claim extractions: `data/reports/faithfulness_validation/evaluation/llm_api/regeneration_attempt_1/claim_extractions.jsonl`
- Explanation IR: `data/reports/explanation_ir/evaluation/explanation_ir.jsonl`

## Summary

- Validated records: 1
- PASS records: 0
- PASS_WITH_WARN records: 1
- FAIL records: 0
- Total claims: 10
- PASS claims: 3
- WARN claims: 7
- FAIL claims: 0

## Join Quality

- Joined records: 1
- Missing IR records: 0

## Per-record Results

| # | Status | IR ID | Explanation ID | Claims | Pass | Warn | Fail |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | PASS_WITH_WARN | `ir_xai_hist_gradient_boosting_v1_163956_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_163956_top_high_risk_163956_attempt_1` | 10 | 3 | 7 | 0 |

## Validator

- Version: `batch_j2_faithfulness_validator_v1.1`
- Mode: `rule_based_ir_faithfulness`
- LLM-as-judge: `false`
