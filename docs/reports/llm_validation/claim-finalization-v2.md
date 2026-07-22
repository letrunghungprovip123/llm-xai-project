# Claim finalization v2

## Frozen validation input

- Path: `data/reports/llm_validation/validation_v1/claim_finalization_v1/claims_final.jsonl`
- SHA-256: `9b53bae17359f3f43415b62f0c7d9f6d9cbda21f2dcac43081bea93d406763f4`
- Claims: **14,680**
- Canonical generations: **648**
- Successful generations: **638**
- Explicit unusable generations: **10**

## Lineage

- Finalizer: `claim_finalizer_v1.1.0`
- Policy: `claim_finalization_policy_v2`
- Extractor: `atomic_claim_extractor_v2.1.0`
- Prompt: `atomic_claim_extraction_prompt_v3`
- Claim schema: `claims_v2`

## Finalization audit

- Changed generations: **157**
- Change records: **1288**
- Atomic count facts: **73/73**
- Atomic count completeness failures: **0**
- Non-claim-bearing policy-absence slots: **5**
- Provider calls during finalization: **0**

Raw generation, extraction, attempt, final-claim and change-log artifacts are
kept locally and excluded from the source repository. Their hashes are retained
in `claim-finalization-v2-summary.json`.
