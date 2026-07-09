# Batch G+ — XAI Evidence Quality Evaluation

## 1. Purpose

Đánh giá chất lượng SHAP evidence trước khi đưa vào Explanation IR v2 và LLM.

## 2. Inputs

- `/Users/hung123/Documents/NghienCuuSau/llm-xai-next/data/reports/xai/xai_local_evidence.jsonl`
- `/Users/hung123/Documents/NghienCuuSau/llm-xai-next/data/reports/xai/xai_evidence_summary.csv`
- `/Users/hung123/Documents/NghienCuuSau/llm-xai-next/data/reports/xai/xai_quality_report.json`
- `/Users/hung123/Documents/NghienCuuSau/llm-xai-next/data/manifests/xai_evidence_manifest.json`
- `/Users/hung123/Documents/NghienCuuSau/llm-xai-next/data/processed/model_ready/tree/X_train_tree.parquet`

## 3. Evaluation Scope

- Scope: pilot/evaluation mode
- Run mode: `evaluation`
- Case count: `120`
- Feature count available in evidence: `213`
- Batch G status: `PASSED`

## 4. Additivity Summary

|   mean_error |   max_error |   passed_count |   failed_count |
|-------------:|------------:|---------------:|---------------:|
|  3.59865e-09 | 8.46225e-09 |            120 |              0 |

## 5. Top-k Coverage

|   k |   mean_coverage |   median_coverage |
|----:|----------------:|------------------:|
|   3 |        0.344454 |          0.354381 |
|   5 |        0.425055 |          0.430448 |
|  10 |        0.566972 |          0.579139 |
|  20 |        0.733282 |          0.741244 |

## 6. Concept-level Aggregation

Top concept groups by total absolute SHAP contribution:

| concept_group                  |   concept_abs_shap |
|:-------------------------------|-------------------:|
| external_score_signal          |          22.759    |
| installment_repayment_behavior |           9.56803  |
| application_profile            |           9.49438  |
| external_credit_history        |           7.32297  |
| loan_affordability             |           6.0773   |
| previous_application_behavior  |           5.95345  |
| applicant_stability            |           4.21579  |
| credit_card_usage_behavior     |           3.69377  |
| pos_cash_behavior              |           3.68891  |
| bureau_monthly_behavior        |           0.835834 |

Concept accounting:

- Mean concept sum error: `2.7639927383897127e-17`
- Max concept sum error: `1.1102230246251565e-16`
- Mean unknown feature group abs share: `0.0`

## 7. Comprehensiveness

Status: `completed`

Reason: `None`

Mean comprehensiveness top10: `0.17654301426088048`

## 8. Sufficiency

Status: `completed`

Reason: `None`

Mean sufficiency drop top10: `0.019553470669350634`

## 9. Stability

Status: `skipped`

Reason: Current Batch G artifact contains one SHAP run only. Stability requires repeated SHAP runs with multiple random seeds/background samples.

## 10. Runtime

| batch_name                                 |   case_count |   feature_count |   runtime_total_seconds |   runtime_per_case_ms |   runtime_per_feature_ms | model_metrics_status   |
|:-------------------------------------------|-------------:|----------------:|------------------------:|----------------------:|-------------------------:|:-----------------------|
| Batch G+ — XAI Evidence Quality Evaluation |          120 |             213 |                 10.8586 |               90.4882 |                 0.424827 | completed              |

## 11. Limitations

- Current scope uses Batch G selected pilot cases.
- Comprehensiveness and sufficiency use median baseline replacement on model-ready features.
- Top-k comprehensiveness currently uses absolute SHAP ranking, not actionability-aware feature filtering.
- Stability is skipped because Batch G currently stores one SHAP run only.

## 12. Next Step

Dùng kết quả Batch G+ để nâng cấp:

- Explanation IR v2
- Evidence Exposure Controller S0-S5
- Multi-LLM Explanation Runner
- Claim-level Faithfulness Evaluation

Final Status

PASSED

Warnings:

- None
