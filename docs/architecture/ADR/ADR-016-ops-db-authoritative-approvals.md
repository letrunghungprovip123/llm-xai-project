# ADR-016 — Ops DB is authoritative for orchestration approvals

## Status

Accepted for ResearchOps Phase 6E.

## Decision

A Prefect resume action is not an approval. The authoritative decision is an
`approvals` record in `llm_xai_ops`, scoped to one pipeline run, Flow Catalog node,
Stage Registry stage, and approval policy.

The protected execution sequence is:

1. Create or reuse the idempotent approval request.
2. Move the pipeline from `RUNNING` to `WAITING_APPROVAL`.
3. Suspend the deployed Prefect flow with typed resume input.
4. Record `APPROVED` or `REJECTED` in PostgreSQL with actor, reason, expiry and audit.
5. Resume the same Prefect flow run.
6. Re-read PostgreSQL and verify the exact approval scope.
7. Continue only for an unexpired `APPROVED` record.

The same Prefect flow-run ID may re-enter the flow after suspension. The Ops bridge
therefore reconnects it to the existing waiting pipeline instead of treating it as
a competing active run.

## Consequences

- UI or CLI resume without a database decision cannot bypass policy.
- Rejected and expired requests fail closed.
- Provider, expensive and release boundaries share one implementation.
- Approval events remain queryable independently of Prefect retention.
