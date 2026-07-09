# Batch J.3 Validation Decision & Feedback Report

Created at: 2026-07-06T03:20:57.016Z
Run mode: `evaluation`
Generator type: `llm_api`

## Summary

- Validation records: 5
- Accepted records: 0
- Accepted with warnings records: 4
- Needs regeneration records: 1
- System error records: 0
- Regeneration feedback records: 1
- Total feedback issues: 4
- Total feedback errors: 1
- Total feedback warnings: 3

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
| 5 | NEEDS_REGENERATION | REGENERATE_BATCH_I | `ir_xai_hist_gradient_boosting_v1_163956_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_163956_top_high_risk_163956` | 2 | 9 | false |

## Output artifacts

- Validation decisions: `/Users/hung123/Documents/NghienCuuSau/llm-xai-next/data/reports/faithfulness_validation/evaluation/llm_api/validation_decisions.jsonl`
- Regeneration feedback: `/Users/hung123/Documents/NghienCuuSau/llm-xai-next/data/reports/faithfulness_validation/evaluation/llm_api/regeneration_feedback.jsonl`
- Feedback summary: `/Users/hung123/Documents/NghienCuuSau/llm-xai-next/data/reports/faithfulness_validation/evaluation/llm_api/regeneration_feedback_summary.json`
- Finalization candidates: `/Users/hung123/Documents/NghienCuuSau/llm-xai-next/data/reports/faithfulness_validation/evaluation/llm_api/finalization_candidates.jsonl`