# Batch J.3 Validation Decision & Feedback Report

Created at: 2026-07-07T03:14:29.001Z
Run mode: `evaluation`
Generator type: `llm_api`

## Summary

- Validation records: 5
- Accepted records: 0
- Accepted with warnings records: 5
- Needs regeneration records: 0
- System error records: 0
- Regeneration feedback records: 0
- Total feedback issues: 0
- Total feedback errors: 0
- Total feedback warnings: 0

## Policy

- Auto loop enabled: `false`
- Calls LLM: `false`
- Calls Bedrock: `false`
- Generate feedback for warnings: `false`
- Next attempt: `1`

## Per-record decisions

| # | Decision | Next action | IR ID | Explanation ID | Errors | Warnings | Can show |
|---:|---|---|---|---|---:|---:|---|
| 1 | ACCEPTED_WITH_WARNINGS | FINALIZE_WITH_WARNINGS | `ir_xai_hist_gradient_boosting_v1_156227_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_156227_top_high_risk_156227` | 0 | 0 | true |
| 2 | ACCEPTED_WITH_WARNINGS | FINALIZE_WITH_WARNINGS | `ir_xai_hist_gradient_boosting_v1_199300_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_199300_top_high_risk_199300` | 0 | 0 | true |
| 3 | ACCEPTED_WITH_WARNINGS | FINALIZE_WITH_WARNINGS | `ir_xai_hist_gradient_boosting_v1_232843_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_232843_top_high_risk_232843` | 0 | 0 | true |
| 4 | ACCEPTED_WITH_WARNINGS | FINALIZE_WITH_WARNINGS | `ir_xai_hist_gradient_boosting_v1_360304_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_360304_top_high_risk_360304` | 0 | 0 | true |
| 5 | ACCEPTED_WITH_WARNINGS | FINALIZE_WITH_WARNINGS | `ir_xai_hist_gradient_boosting_v1_163956_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_163956_top_high_risk_163956` | 0 | 0 | true |

## Output artifacts

- Validation decisions: `data/reports/faithfulness_validation/evaluation/llm_api/base/validation_decisions.jsonl`
- Regeneration feedback: `data/reports/faithfulness_validation/evaluation/llm_api/base/regeneration_feedback.jsonl`
- Feedback summary: `data/reports/faithfulness_validation/evaluation/llm_api/base/regeneration_feedback_summary.json`
- Finalization candidates: `data/reports/faithfulness_validation/evaluation/llm_api/base/finalization_candidates.jsonl`