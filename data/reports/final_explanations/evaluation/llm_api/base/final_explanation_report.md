# Batch K Final Explanation Report

Created at: 2026-07-07T03:46:45.257Z
Status: **PASS**

## Summary

- Finalization candidates: 5
- Finalized records: 0
- Finalized with warnings records: 5
- Blocked records: 0
- Records can show to user: 5
- Records with errors: 0
- Records with warnings: 0

## Policy

- Calls LLM: `false`
- Calls Bedrock: `false`
- Only finalize `can_show_to_user=true`: `true`

## Per-record finalization

| # | Status | Can show | IR ID | Explanation ID | Faithfulness | Errors | Warnings |
|---:|---|---|---|---|---|---:|---:|
| 1 | FINALIZED_WITH_WARNINGS | true | `ir_xai_hist_gradient_boosting_v1_156227_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_156227_top_high_risk_156227` | PASS_WITH_WARN | 0 | 0 |
| 2 | FINALIZED_WITH_WARNINGS | true | `ir_xai_hist_gradient_boosting_v1_199300_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_199300_top_high_risk_199300` | PASS_WITH_WARN | 0 | 0 |
| 3 | FINALIZED_WITH_WARNINGS | true | `ir_xai_hist_gradient_boosting_v1_232843_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_232843_top_high_risk_232843` | PASS_WITH_WARN | 0 | 0 |
| 4 | FINALIZED_WITH_WARNINGS | true | `ir_xai_hist_gradient_boosting_v1_360304_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_360304_top_high_risk_360304` | PASS_WITH_WARN | 0 | 0 |
| 5 | FINALIZED_WITH_WARNINGS | true | `ir_xai_hist_gradient_boosting_v1_163956_top_high_risk` | `llm_api_ir_xai_hist_gradient_boosting_v1_163956_top_high_risk_163956` | PASS_WITH_WARN | 0 | 0 |

## Output artifacts

- Final explanations: `data/reports/final_explanations/evaluation/llm_api/base/final_explanations.jsonl`
- Summary JSON: `data/reports/final_explanations/evaluation/llm_api/base/final_explanation_summary.json`
- Summary CSV: `data/reports/final_explanations/evaluation/llm_api/base/final_explanation_summary.csv`
- Manifest: `data/reports/final_explanations/evaluation/llm_api/base/final_explanation_manifest.json`
