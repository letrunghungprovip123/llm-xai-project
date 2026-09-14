# Candidate validator primary with declared limitation

- **Status:** Accepted
- **Scope:** LLM-XAI ResearchOps architecture

## Context

The repository needs one explicit, reproducible boundary for this responsibility.
Leaving the decision implicit would create competing sources of truth.

## Decision

The candidate claim-measurement release is the primary operational condition, while human-ground-truth claims remain prohibited until calibration supports them.

## Consequences

- The decision is versioned and reviewable in Git.
- Runtime services must preserve the recorded identity and provenance.
- A future incompatible choice must supersede this ADR explicitly.
