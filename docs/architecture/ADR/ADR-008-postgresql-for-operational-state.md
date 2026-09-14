# PostgreSQL for operational state

- **Status:** Accepted
- **Scope:** LLM-XAI ResearchOps architecture

## Context

The repository needs one explicit, reproducible boundary for this responsibility.
Leaving the decision implicit would create competing sources of truth.

## Decision

Mutable run status, approvals, audit events and lineage indexes require transactional relational storage.

## Consequences

- The decision is versioned and reviewable in Git.
- Runtime services must preserve the recorded identity and provenance.
- A future incompatible choice must supersede this ADR explicitly.
