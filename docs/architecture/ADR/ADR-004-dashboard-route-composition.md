# Nine conceptual sections map to seven routes

- **Status:** Accepted
- **Scope:** LLM-XAI ResearchOps architecture

## Context

The repository needs one explicit, reproducible boundary for this responsibility.
Leaving the decision implicit would create competing sources of truth.

## Decision

The application consolidates related conceptual sections while preserving exact RQ and dataset coverage through a composition contract.

## Consequences

- The decision is versioned and reviewable in Git.
- Runtime services must preserve the recorded identity and provenance.
- A future incompatible choice must supersede this ADR explicitly.
