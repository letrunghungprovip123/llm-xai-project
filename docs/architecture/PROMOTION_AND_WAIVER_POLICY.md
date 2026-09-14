# Governed Promotion and Waiver Policy — Phase 7C

Phase 7C replaces ad-hoc release checks and hard-coded MLflow gate lists with one governed policy engine. The policy catalog is versioned in Git, evaluated against immutable gate histories, and records an auditable decision snapshot before mutating a release or an MLflow alias.

## Boundary

```text
verified artifact reports
  → immutable gate_evaluations
  → current gate_results projection
  → governed promotion policy
  → approval and waiver authorization
  → promotion_decision snapshot
  → release transition or MLflow alias saga
```

A promotion service never parses scientific reports. That responsibility belongs to Phase 7B adapters. It only consumes current gate projections whose `current_evaluation_id` points to immutable Phase 7A evidence.

## Governed policy catalog

`config/platform/promotion_policies_v1.json` maps exactly one policy to each supported target kind. A policy declares:

- eligible source states and target state;
- the complete required-gate set;
- non-waivable gates;
- whether a failed gate can produce `READY_WITH_LIMITATIONS`;
- approval policy and separation-of-duties requirement;
- explicitly permitted external side effects.

The governance validator verifies that every required gate exists in the Gate Catalog and that release transitions are allowed by the lifecycle contract.

## Gate authorization

Authorization is fail closed:

```text
missing gate                         → reject
no current immutable evaluation      → reject
PENDING or FAILED                    → reject
WAIVED without active matching waiver→ reject
waiver bound to an older evaluation  → reject
non-waivable gate                    → reject
expired/revoked waiver               → reject
wrong target state for active waiver → reject
```

A waiver never edits `GateEvaluation.outcome`. The scientific outcome remains `FAILED`; only the mutable gate projection has `effective_status=WAIVED`.

## Approval scope

Promotion approval identity is exact:

```text
(target_type, target_id, approval_policy)
```

Waiver approval identity is exact:

```text
("gate_result", gate_result_id, waiver_approval_policy)
```

Approved records must not be expired and must have a distinct requester and decision actor when separation of duties is enabled.

## Immutable decision snapshot

Before execution, `promotion_decisions` records:

- policy ID, version and catalog SHA-256;
- expected and target state;
- current gate evaluation IDs and effective states;
- approval snapshot;
- active waiver snapshot;
- request identity and idempotency digest.

Reusing an idempotency key with different semantics raises identity drift. Replaying an identical completed request returns the existing decision without repeating side effects.

## Release transition

Release promotion is transactional inside the Ops DB:

```text
validate manifest/membership
→ authorize gates/waivers/approval
→ record PENDING decision
→ expected-state transition
→ record previous/new state
→ audit
→ COMPLETED
```

An active waiver can only move an eligible release to `READY_WITH_LIMITATIONS`. Certification without active waivers moves to `CERTIFIED`.

## MLflow alias saga

PostgreSQL and MLflow cannot share one ACID transaction. Model promotion therefore uses a governed saga:

```text
validate candidate and source-manifest tag
→ authorize exact model-version gates
→ record PENDING decision
→ snapshot candidate/champion aliases
→ archive previous champion reference
→ assign champion alias
→ tag promoted version
→ verify alias persisted
→ audit and mark COMPLETED
```

If a failure occurs after an external mutation, the decision is marked `FAILED_PARTIAL` with `reconciliation_required=true`. The prior and observed external states remain available for a safe reconciliation action.

## CLI

```bash
python3 -m research.python.researchops.promotion validate-policies
python3 -m research.python.researchops.promotion inspect-policy \
  --target-type release --target-kind thesis_report

python3 -m research.python.researchops.promotion grant-waiver ...
python3 -m research.python.researchops.promotion revoke-waiver ...
python3 -m research.python.researchops.promotion promote-release ...
python3 -m research.python.researchops.promotion promote-model ...
```

Database commands require `RESEARCHOPS_DATABASE_URL`; model promotion also requires the MLflow environment contract.

## Non-goals

Phase 7C does not:

- parse validator reports;
- create semantic evaluations manually;
- expose HTTP endpoints;
- implement portal authorization;
- permit model champion promotion with waived gates;
- make a database transaction span MLflow.
