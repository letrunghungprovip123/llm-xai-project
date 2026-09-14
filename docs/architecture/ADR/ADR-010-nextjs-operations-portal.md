# Next.js is an operations portal

- **Status:** Accepted
- **Scope:** LLM-XAI ResearchOps architecture

## Context

The repository needs one explicit, reproducible boundary for this responsibility.
Leaving the decision implicit would create competing sources of truth.

## Decision

Next.js will expose runs, releases, artifacts, gates, cases and reviews. It will not rewrite the certified Dash analytical surface.

## Consequences

- The decision is versioned and reviewable in Git.
- Runtime services must preserve the recorded identity and provenance.
- A future incompatible choice must supersede this ADR explicitly.
