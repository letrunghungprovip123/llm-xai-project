# ADR-013 — Phase 5 idempotency and reconciliation

## Status

Accepted for the Phase 5 closure checkpoint.

## Decision

Phase 5 retries use stable tracking keys derived from the source artifact,
manifest hash, stage identity, source commit, contract version, and model key.

- Zero matches create a run/version.
- One consistent match is reused.
- Duplicate or conflicting matches fail closed.
- Candidate promotion is not automatic.
- Reconciliation is report-only by default and detects missing runs/versions,
  manifest-hash mismatch, alias drift, duplicate tracking keys, and orphan
  active model versions.
- Reconciliation never deletes model bytes, runs, receipts, or certified
  artifacts.

Machine callers consume explicit atomic `--report-path` JSON documents. Human
stdout/stderr, including MLflow progress and UI links, is not parsed as an API.
