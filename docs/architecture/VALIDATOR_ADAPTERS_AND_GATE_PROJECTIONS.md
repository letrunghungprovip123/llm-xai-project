# Validator Adapters and Gate Projections — Phase 7B

Phase 7B converts verified scientific reports into the normalized, immutable
`gate_evaluation_v1` contract introduced in Phase 7A. It does not decide
promotion eligibility and it does not mutate scientific artifacts.

## Trust boundary

```text
verified artifact package
→ canonical report declared by the Stage Registry
→ versioned pure adapter
→ immutable artifact-scoped gate evaluation
→ lineage-preserving derived projections
```

Adapters never scan the repository for an arbitrary latest report. The report
must be inside the verified artifact package and must match the Stage Registry
`verification.report_glob`. Ambiguous matches fail closed.

## Adapter families

The registry includes explicit, versioned adapters for manifest-style reports,
standard check reports, model training/readiness, XAI quality, generation
manifests, claim-validation release gates, dashboard certification, MLflow
registration receipts, environment verification, artifact integrity, and
complete release bundles.

An unsupported report shape, unknown schema, missing semantic signal, or
adapter/contract mismatch raises a contract error. Adapters are deterministic
and have no database, MLflow, or network side effects.

## Projection rules

1. The source semantic evaluation is recorded on the verified output artifact.
2. A stage-run projection is derived from that evaluation and retains
   `source_evaluation_ids`.
3. Model-ready and XAI-quality evaluations are projected to the exact
   `trained_model` ancestor.
4. The MLflow receipt projects gates to the exact model-version identity using
   its `source_model_artifact_id`; gates from unrelated training runs cannot be
   mixed.
5. Release-scoped projections require a release record and artifact membership.

Every projection is another immutable evaluation. A projection is never a
manual `GateResult` insertion.

## Failed command evidence

A scientific command can write a useful validation report and still exit
nonzero. The executor stores changed files declared by
`failure_evidence_globs` under the immutable `stage_execution_evidence`
artifact. The matching adapter records a `FAILED` stage-run evaluation while
the stage remains failed. The report is not registered as a successful
scientific output.

## Phase boundary

Phase 7B records evidence and deterministic projections only. Required gate
sets, waiver authorization, approval checks, and promotion side effects belong
to Phase 7C.
