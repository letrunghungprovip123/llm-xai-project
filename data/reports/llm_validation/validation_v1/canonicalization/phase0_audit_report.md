# Phase 0 — Input Audit and Canonicalization

Status: **PASSED_WITH_WARNINGS**

## Canonical matrix

| Model | Planned | Actual | Usable | Unusable |
|---|---:|---:|---:|---:|
| qwen3_8b | 216 | 216 | 216 | 0 |
| deepseek_v4_flash | 216 | 216 | 213 | 3 |
| phi4_mini_instruct | 216 | 216 | 209 | 7 |
| **Main total** | **648** | **648** | **638** | **10** |
| template_baseline | 216 | 216 | 216 | 0 |

## Preserved unusable records

- `run_deepseek_eval_001__deepseek_v4_flash__r1__pkg_S4_ir_xai_hist_gradient_boosting_v1_310672_near_threshold` — truncated_response, finish_reason_length, raw_json_parse_failed, schema_invalid, schema_validation_errors, parsed_output_missing
- `run_deepseek_eval_001__deepseek_v4_flash__r1__pkg_S4_ir_xai_hist_gradient_boosting_v1_441551_near_threshold` — truncated_response, finish_reason_length, raw_json_parse_failed, schema_invalid, schema_validation_errors, parsed_output_missing
- `run_deepseek_eval_001__deepseek_v4_flash__r1__pkg_S4_ir_xai_hist_gradient_boosting_v1_280694_near_threshold` — truncated_response, finish_reason_length, raw_json_parse_failed, schema_invalid, schema_validation_errors, parsed_output_missing
- `run_phi4_mini_eval36_r1_pinned__phi4_mini_instruct__r1__pkg_S4_ir_xai_hist_gradient_boosting_v1_342859_low_risk` — truncated_response, finish_reason_length, raw_json_parse_failed, schema_invalid, schema_validation_errors, parsed_output_missing
- `run_phi4_mini_eval36_r1_pinned__phi4_mini_instruct__r1__pkg_S4_ir_xai_hist_gradient_boosting_v1_125223_low_risk` — truncated_response, finish_reason_length, raw_json_parse_failed, schema_invalid, schema_validation_errors, parsed_output_missing
- `run_phi4_mini_eval36_r1_pinned__phi4_mini_instruct__r1__pkg_S4_ir_xai_hist_gradient_boosting_v1_110178_true_positive` — truncated_response, finish_reason_length, raw_json_parse_failed, schema_invalid, schema_validation_errors, parsed_output_missing
- `run_phi4_mini_eval36_r1_pinned__phi4_mini_instruct__r1__pkg_S4_ir_xai_hist_gradient_boosting_v1_449188_false_positive` — truncated_response, finish_reason_length, raw_json_parse_failed, schema_invalid, schema_validation_errors, parsed_output_missing
- `run_phi4_mini_eval36_r1_pinned__phi4_mini_instruct__r1__pkg_S4_ir_xai_hist_gradient_boosting_v1_175570_false_negative` — truncated_response, finish_reason_length, raw_json_parse_failed, schema_invalid, schema_validation_errors, parsed_output_missing
- `run_phi4_mini_eval36_r1_pinned__phi4_mini_instruct__r1__pkg_S4_ir_xai_hist_gradient_boosting_v1_452391_false_negative` — truncated_response, finish_reason_length, raw_json_parse_failed, schema_invalid, schema_validation_errors, parsed_output_missing
- `run_phi4_mini_eval36_r1_pinned__phi4_mini_instruct__r1__pkg_S4_ir_xai_hist_gradient_boosting_v1_310672_near_threshold` — truncated_response, finish_reason_length, raw_json_parse_failed, schema_invalid, schema_validation_errors, parsed_output_missing

## Audit warnings

- **selection_source_not_reproducible_from_uploaded_subset** (provenance): The selection manifest references the full 120-case evidence source, which is not part of the Phase 0 input bundle. The supplied 36-case subset and selection CSV are internally consistent, but the original selection cannot be rerun from this bundle alone.
- **selected_case_csv_hash_not_recorded_in_selection_manifest** (provenance): The selection manifest names selected_case_ids_36.csv but does not store its SHA-256 hash.
- **concept_claim_policy_vs_allowlist_mismatch** (contract): Concept claims are enabled and concept metadata is exposed, while allowed_concept_ids is empty. Affected packages: 72.
- **s5_exposed_features_outside_allowed_feature_ids** (contract): S5 prompt payloads expose selected feature evidence that is not present in the S5 allowed_feature_ids list. Affected packages: 36.
- **restricted_registry_features_exposed_to_prompts** (privacy_contract): Features marked sensitive or limited in feature_registry.csv occur in selected evidence supplied to the narrative prompt. Affected packages: 177.

## Phase 0 boundary

No semantic validator was run. Phase 0 only canonicalizes official records and checks syntax, identity, hashes, cohort completeness, prompt parity, and observed package-contract inconsistencies.
