# Deterministic claim validation v3

## Decision

The local deterministic validation foundation is complete and suitable as an
input to a later metric-construction phase. This decision means conformance to
the frozen deterministic specification; it is not a claim of universal
semantic truth.

Validator source commit:
`5f3dde609a76709e118b62f01a1aec047360dcbe`.

## Why v3 was required

The frozen v2 schema required at least one evidence identity
(`source_evidence_id` or `package_id`) for every result. A later v2
implementation moved that requirement into the SUCCESS branch, which changed
the frozen contract so that a pre-evidence terminal ERROR could carry both
identities as null. That behavior is useful, but it is a semantic contract
change.

The remediation restored `claim_validation_v2.schema.json` to its frozen
meaning and introduced `claim_validation_v3.schema.json`. V3 keeps the global
result shape, requires evidence identity for SUCCESS, and permits both evidence
identities to be null for ERROR while requiring a terminal error object and a
null semantic status. V2 remains historical and unchanged relative to its
frozen foundation commit.

## Runtime boundaries and architecture

All canonical generation rows and Evidence Packages enter the validator as
unknown JSON. Validation-specific parsers construct narrow runtime views and
fail closed on missing identifiers, malformed nested objects, invalid
directions, non-finite numerics, invalid ranks, inconsistent nested identity,
and incomplete unusable-generation metadata. The parser does not expose hidden
IR fields to semantic validators.

The orchestration path is visibly:

`load → verify lock → parse → index → select → validate → schema-check →
reconcile → aggregate → atomically write`

Implementation responsibilities are separated into runtime parsers, indexes,
selection, validation execution, result construction, reconciliation,
aggregation/output, and claim-family validators. Pure claim-family validators
perform no file I/O and do not mutate imported policy or shared configuration.

## Evidence boundary and claim behavior

The only semantic evidence source is the exact canonical Evidence Package shown
to the model. Hidden IR, another evidence level, another generation, registry
membership, and unselected features or concepts cannot rescue a claim.

At S0, only prediction evidence is exposed. Feature presence/direction,
concept presence/direction, ranking, and magnitude therefore cannot be
SUPPORTED. Prediction, feature/concept identity and direction, numeric values,
ranking, magnitude, uncertainty, distributed-evidence statements,
recommendations, limitations, and causal/guarantee language are routed through
their frozen claim-type policy and reason taxonomy. Direction uses the frozen
near-zero threshold `1e-12`. Prediction-score percentages use the frozen
half-display-unit absolute tolerance `0.00005`.

## Critical oracle and boundary coverage

The human-authored oracle contains 24 semantic fixtures across all 13 claim
types and all five valid semantic statuses, plus terminal generation/evidence
join ERROR shapes and the missing-direction-source branch. It covers all MATCH
reasons, all three hard-safety reasons, missing feature/concept/rank/magnitude
sources, reversed/neutral/mixed direction, ranking ties, unsupported
magnitude/recommendation, unavailable prediction value, numeric supported,
unsupported, and contradicted outcomes, and causal overclaim.

Separate boundary tests cover both sides of `±1e-12`, both sides and the exact
point of `0.00005`, all six S0-prohibited claim families, malformed generation
and Evidence Package inputs, duplicate indexes, and reconciliation failures.
The oracle and boundary checks passed without changing expected values to fit
observed implementation output.

## Critical mutation catalog

All 16 controlled mutations were killed (`16/16 = 1.000`):

| Mutation | Detecting assertion |
|---|---|
| M1 S0 hidden feature | S0 returns `FEATURE_NOT_EXPOSED` |
| M2 reversed normalization | exposed plural direction normalizes to the claimed singular direction |
| M3 epsilon changed to zero | `1e-12` remains neutral |
| M4 tolerance widened | `0.0001`-scale prediction delta remains outside tolerance |
| M5 outside tolerance supported | reason mapping remains CONTRADICTED |
| M6 registry rescues concept | absent exposed concept remains not found |
| M7 ERROR semantic status | v3 schema rejects the mutant |
| M8 SUCCESS missing status | v3 schema rejects the mutant |
| M9 failed join dropped | one-result-per-claim reconciliation rejects it |
| M10 duplicate last-write-wins | unique index rejects duplicate keys |
| M11 timestamp in validation ID | timestamp-mutated identity differs from the stable ID |
| M12 input-order output | reversed input produces identical selected output |
| M13 unusable generations dropped | aggregation retains the unusable row with zero claims |
| M14 causal SHAP supported | causal wording remains `CAUSAL_OVERCLAIM` |
| M15 unknown reason accepted | taxonomy lookup rejects it |
| M16 upstream bytes mutated | locked SHA differs from mutated bytes |

## Required test matrix

The required validation matrix passed:

- TypeScript research-project typecheck;
- v2/v3 contract compatibility;
- strict runtime parser tests;
- human-authored oracle and boundary tests;
- property/metamorphic tests;
- all 16 mutation detectors;
- pipeline, exact join, reconciliation, and aggregation tests;
- claim-finalization regression tests;
- frozen policy, reason taxonomy, and numeric policy tests;
- required-mode golden tests (`10/10`);
- readiness-schema and internal-consistency tests;
- CLI help exposing `llm:validate`.

The combined required matrix reported `176/176` passing tests; the separate
required-mode golden command reported `10/10`.

Two tests in `tests/llmValidation/claimExtraction.test.ts` fail when run
separately:

1. `claim extraction rejects source text outside the declared section` —
   `AssertionError [ERR_ASSERTION]: Missing expected exception.`
2. `runner audits a failed response, retries it and then reuses success` —
   `AssertionError [ERR_ASSERTION]: Expected values to be strictly equal: 1 !== 0`

They exercise claim-extraction span rejection and extraction runner retry/audit
reuse, respectively. The required deterministic-validator gate covers the v3
contract, validation input parsers, deterministic routes, joins,
reconciliation, aggregation, finalization regression, and frozen
policy/golden checks; it does not make either extraction behavior a required
validator gate. They were reproduced and reported as instructed, not fixed,
and are not described here as pre-existing because no historical proof was
established in this remediation.

## Balanced smoke

Two independent 100-claim smoke runs used new directories and no force
overwrite. The cohort covers all three models, all six evidence levels, all
three claim origins, all 12 claim types present in official data, and 12 S0
claims. Causal remains synthetic because its official count is zero.

- Result count: `100` in each run.
- Execution errors: `0`.
- Generation rows: `648`.
- Result SHA-256:
  `48c218717401904ba922e905275fbbfd574dfa02691f4b5ebc4f7aa06efa7fa7`.
- Result JSONL, deterministic summary, reason CSV, and generation summary:
  byte-identical.

## Full validation and reconciliation

Two independent full runs used new directories and no force overwrite.

- Input claims: `14,680`.
- Output results: `14,680`.
- Unique input claim IDs: `14,680`.
- Unique output claim IDs: `14,680`.
- Unique validation IDs: `14,680`.
- Missing/unexpected/duplicate results: `0/0/0`.
- V3 schema failures: `0`.
- Execution errors: `0`.
- Result SHA-256 for both runs:
  `df2676f4d6ae14957ecd5d001ac95f5091bea5c473b95738a23afa801024b6fa`.
- Result JSONL, deterministic summary, reason CSV, and generation summary:
  byte-identical.

Observed semantic status counts (descriptive, not frozen test targets):

| Status | Count |
|---|---:|
| SUPPORTED | 14,230 |
| UNSUPPORTED | 147 |
| CONTRADICTED | 91 |
| NOT_VERIFIABLE | 212 |

All emitted reason codes exist in the frozen taxonomy. Every result conforms to
the reason execution/status/claim-type mapping. SUPPORTED uses only MATCH
reasons; ERROR with semantic status, SUCCESS without semantic status,
`PARTIALLY_SUPPORTED`, unknown reasons, and unknown claim types all have count
zero. The frozen hard-safety set is exactly `CAUSAL_OVERCLAIM`,
`CERTAINTY_OVERCLAIM`, and `GUARANTEE_OVERCLAIM`; no hard-safety event occurred
in the official cohort.

A deterministic stratified plausibility sample inspected 15 records from each
of SUPPORTED, UNSUPPORTED, CONTRADICTED, and NOT_VERIFIABLE (`60/60` total).
It covered all models and S0–S5, multiple origins, claim types, and every reason
family present in the chosen strata. Expected and observed facts were
consistent with the status and exact exposed evidence in every sampled record.
There were no ERROR records to inspect.

## S0 invariant proof

SUPPORTED at S0 is zero separately for every prohibited family:

| Claim type | Count |
|---|---:|
| feature_presence | 0 |
| feature_direction | 0 |
| concept_presence | 0 |
| concept_direction | 0 |
| ranking | 0 |
| magnitude | 0 |

## Generation aggregation

The generation output contains exactly 648 rows: 638 usable and 10 unusable.
The separate template baseline denominator remains 216. Every usable row keeps
generation identity and all semantic/error/hard-safety/reason-family counts.
Every unusable row remains present with `total_claims = 0`, the exact failure
reason, and canonical contract-usability metadata. No claim metric was
fabricated for an unusable generation.

Generation-summary SHA-256:
`2c3309c84b0a4e587e02050292118a7a0b2b18c1b2a5247de24f1a5413c979e6`.

## Metric readiness

The machine-readable readiness artifact is:

`data/reports/llm_validation/validation_v1/claim_validation_v3_a/claim_validation_metric_readiness_v1.json`

It records the source and input lineage, output hashes and counts, determinism
comparison, S0 proof, hard-safety mapping, all 18 binary gates, limitations,
and known legacy failures. Its schema and cross-field consistency are tested.
`metric_ready` is true only when `min(G1..G18) = 1.000`.

Readiness artifact SHA-256:
`bf354f4b9f1b7584338147b45156c379c0777a061770582ee59dd08185c76822`.

## Limitations

- No human calibration.
- No inter-rater agreement.
- No semantic LLM judge.
- No bootstrap.
- No non-inferiority analysis.
- No universal real-world 100% truth claim.
- “100%” refers only to deterministic specification conformance.
