# Deterministic claim validation v1

## Objective

This run validates every atomic `claims_v2` record against the exact canonical
Evidence Package shown to its source generation. It is a local, deterministic,
descriptive validation pass. It does not call a provider, consult hidden
Explanation IR, or perform model selection.

## Frozen inputs

The source of truth is
`config/research/ts-validation/validation_input_lock_v1.json`.

| Artifact | Records | SHA-256 |
| --- | ---: | --- |
| Canonical Evidence Packages | 216 | `37c25b261d496e7c9bf50a62141f93b5544a45af43208918d0eaf589d6307117` |
| Main canonical generations | 648 | `252edae8dd920c259a1da74d7b2f09b26558b994e01b3cd29dd60c0d6f9086ec` |
| Template baseline | 216 | `4d8e2e4c5d644ab33733d5bb2251bd1d6ebbb21588f662d709a0f01ee992de15` |
| Extracted claims | 14,640 | `216410f98ed3b7f43430eb34da17bb1e3b0928d561031bc37c2b8b0aa20f371c` |
| Extraction attempts | 680 | `b877911ce8983413a9a11d8607503b9339d82bb2855f71178333f11904b5e6a0` |
| Extraction failures | 10 | `c77788d8ac5e0ab2d309487d2f5499bdf6876137fc8e46ead479642c625f5add` |
| Finalized claims | 14,680 | `9b53bae17359f3f43415b62f0c7d9f6d9cbda21f2dcac43081bea93d406763f4` |
| Finalization changes | 1,288 | `ee819a5cbc91f69d2987b4a4894b3ef817be3eed6432d26b4198b571f573d97e` |
| Finalization manifest | 1 | `d1cdc08ddb592d83dabff6991e6d7b7e68462738a15e7e4393c3642e3da7962d` |

The lock loader verifies every count and digest before validation. The hashes
above were unchanged after smoke and full validation.

## Architecture and evidence boundary

The pipeline loads the frozen lock, validates `claims_v2`, loads the canonical
generation index and Evidence Packages, rejects duplicate keys, and joins:

```text
claim.generation_id -> generation.generation_id
generation.package_id -> evidence.package_id
```

It also requires exact agreement for case, model, evidence level, repeat,
`source_ir_id`, and `source_evidence_id`. Only `prompt_payload` fields in the
joined Evidence Package are used as validation facts. Allowed feature and
concept IDs constrain the exposed subsets. Full Explanation IR, feature
registries, other evidence levels, and other generations are prohibited.

Each selected claim is routed by its frozen claim type. Before output, its
reason/status combination is checked against
`claim_validation_policy_v1` and `claim_validation_reason_codes_v1`, then the
complete record is validated against `claim_validation_v2`. Results are sorted
by `claim_id`, use deterministic IDs, and are written through a staging
directory followed by atomic rename. Existing output directories are rejected
when `--force=false`.

## Status and reason taxonomy

Execution status is `SUCCESS` or `ERROR`. Semantic status is one of
`SUPPORTED`, `UNSUPPORTED`, `CONTRADICTED`, `NOT_VERIFIABLE`, or
`NOT_APPLICABLE`; `PARTIALLY_SUPPORTED` is not used.

The active reason taxonomy contains 49 codes. Only `EXACT_MATCH`,
`NORMALIZED_MATCH`, and `TOLERANCE_MATCH` produce `SUPPORTED`. System reasons
produce execution errors only. The hard-safety set remains exactly
`CAUSAL_OVERCLAIM`, `GUARANTEE_OVERCLAIM`, and `CERTAINTY_OVERCLAIM`.

## Numeric and direction rules

Direction comparison normalizes `increases_risk`/`decreases_risk` to
`increase_risk`/`decrease_risk`. Absolute SHAP values at or below `1e-12` are
neutral. Reversed direction is contradicted; missing, mixed, or unknown source
direction is not verifiable. S0 cannot expose feature or concept direction.

Prediction score and threshold values are normalized to `[0,1]` and use the
frozen absolute tolerance `0.00005`. Counts and ranks require exact integer
equality. Feature values and other values without a reliable display precision
are `NOT_VERIFIABLE`; no tolerance is invented.

## Balanced smoke

Command:

```bash
npm run research -- llm:validate -- \
  --input-lock config/research/ts-validation/validation_input_lock_v1.json \
  --output-dir data/reports/llm_validation/validation_v1/claim_validation_smoke_v1 \
  --mode deterministic \
  --smoke true \
  --smoke-limit 100 \
  --force false
```

The deterministic cohort contained 100 claims and covered all three models,
all six evidence levels, all three claim origins, and all 12 claim types present
in the official input. The absent causal type was covered synthetically.

| Status | Count |
| --- | ---: |
| Supported | 85 |
| Unsupported | 10 |
| Contradicted | 1 |
| Not verifiable | 4 |
| Not applicable | 0 |
| Execution error | 0 |

The smoke results SHA-256 is
`dab2406b7511adba8d7ef51272f015413d5f964adea67a65f5644fbf1c57be11`.
An independent rerun produced a byte-identical result JSONL.

## Full validation

Command:

```bash
npm run research -- llm:validate -- \
  --input-lock config/research/ts-validation/validation_input_lock_v1.json \
  --output-dir data/reports/llm_validation/validation_v1/claim_validation_v1 \
  --mode deterministic \
  --force false
```

Reconciliation:

```text
input claims                 14,680
output terminal results      14,680
unique input claim IDs       14,680
unique output claim IDs      14,680
unique validation IDs        14,680
missing / unexpected IDs     0 / 0
execution errors             0
```

The result JSONL SHA-256 is
`9821eb49238f3a3f2ce8415ed898680d083e8859acd5bffdd593ca3cb926599d`.
An independent full rerun produced a byte-identical result JSONL.

### Overall status

| Status | Count | Rate over 14,680 |
| --- | ---: | ---: |
| Supported | 14,230 | 96.93% |
| Unsupported | 147 | 1.00% |
| Contradicted | 91 | 0.62% |
| Not verifiable | 212 | 1.44% |
| Not applicable | 0 | 0.00% |

No hard-safety failure was observed in the frozen official claims. All three
hard-safety paths, including the zero-record causal route, remain covered by
synthetic tests.

### By model

Rates use each model's claim count as the explicit denominator.

| Model | Claims | Supported | Unsupported | Contradicted | Not verifiable | Supported rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DeepSeek | 5,393 | 5,153 | 27 | 41 | 172 | 95.55% |
| Phi | 4,371 | 4,272 | 46 | 33 | 20 | 97.74% |
| Qwen | 4,916 | 4,805 | 74 | 17 | 20 | 97.74% |

These are descriptive observations on the frozen cohort, not statistical
comparisons.

### By evidence level

| Level | Claims | Supported | Unsupported | Contradicted | Not verifiable | Supported rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S0 | 390 | 369 | 18 | 2 | 1 | 94.62% |
| S1 | 2,781 | 2,602 | 24 | 17 | 138 | 93.56% |
| S2 | 2,643 | 2,588 | 41 | 5 | 9 | 97.92% |
| S3 | 2,554 | 2,501 | 42 | 2 | 9 | 97.92% |
| S4 | 4,032 | 3,924 | 15 | 49 | 44 | 97.32% |
| S5 | 2,280 | 2,246 | 7 | 16 | 11 | 98.51% |

### Reason codes

The most frequent reasons were `EXACT_MATCH` (8,567),
`NORMALIZED_MATCH` (5,190), `TOLERANCE_MATCH` (473),
`NUMERIC_ROLE_UNSUPPORTED` (165), `UNSUPPORTED_RECOMMENDATION` (77),
`DIRECTION_REVERSED` (67), and `CONCEPT_NOT_FOUND_IN_EVIDENCE` (64).
All counts are descriptive.

## Generation aggregation

`generation_validation_summary.jsonl` contains exactly 648 main-generation
rows: 638 usable and 10 unusable. The unusable rows have `total_claims=0` and
retain runtime, truncation, JSON-parse, schema, and usability reasons; claim
metrics are not fabricated. The 216 Template baseline generations remain a
separate denominator and are not included.

## Outputs

Each smoke and full output directory contains:

```text
claim_validation_results.jsonl
claim_validation_manifest.json
claim_validation_summary.json
reason_code_counts.csv
generation_validation_summary.jsonl
validation_execution_errors.jsonl
```

Unsupported and contradicted claims are semantic results, not execution
failures.

## Limitations and future work

This stage has no human calibration, no inter-rater agreement, no paired
bootstrap, and no non-inferiority analysis. Results are deterministic and
descriptive only. They do not establish a final model, a minimum sufficient
evidence level, statistical superiority, or deployment readiness.

Future work may add a separately versioned human-calibration protocol,
inter-rater analysis, paired bootstrap, and non-inferiority analysis. Those
steps must not retroactively change this frozen deterministic result.
