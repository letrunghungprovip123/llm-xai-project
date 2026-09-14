# ADR-017 — Prefect and Ops DB reconciliation is report-first and repair-safe

## Status

Accepted for ResearchOps Phase 6E.

## Decision

Prefect owns scheduler and task state; PostgreSQL `llm_xai_ops` owns governed run
identity, audit, approvals and artifact bindings. A reconciliation service compares
the two systems and emits a structured report.

`report-only` is the default and performs no persistent mutation. `repair-safe` may
only:

- expire a verifiably stale approval;
- fail a pipeline still waiting on that expired approval;
- backfill `FAILED` or `CANCELLED` from a uniquely bound terminal Prefect run.

It never deletes runs or artifacts, rewrites scientific results, marks a pipeline
successful without its immutable receipt, approves work, or promotes a release.

## Consequences

- Drift is visible without making repair the default.
- Successful scientific state cannot be inferred from scheduler state alone.
- Missing receipts, outputs, environments and bindings remain blocking errors.
- Repair behavior is narrow, deterministic and auditable.
