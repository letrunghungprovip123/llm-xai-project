# Visualization release is the Dash source of truth

- **Status:** Accepted
- **Scope:** LLM-XAI ResearchOps architecture

## Context

The repository needs one explicit, reproducible boundary for this responsibility.
Leaving the decision implicit would create competing sources of truth.

## Decision

Dash reads the frozen visualization-data-v2 release and does not recalculate inferential results.

## Consequences

- The decision is versioned and reviewable in Git.
- Runtime services must preserve the recorded identity and provenance.
- A future incompatible choice must supersede this ADR explicitly.
