# ADR-014 — Bind Prefect execution to Ops DB and immutable evidence

## Status

Accepted for ResearchOps Phase 6C.

## Decision

Prefect run identifiers are orchestration references, not scientific identity.
Every Prefect flow/task invocation is bound to a stable ResearchOps
orchestration key in `llm_xai_ops` through `orchestration_bindings`.

A flow key is derived from the flow/stage registry locks, immutable input
manifest identities, canonical parameters, source commit, and dependency lock.
A stage key additionally includes the node and stage version. Exact successful
keys are reused; active duplicates fail closed; failed keys create a new
explicit attempt only when retry policy permits.

Every terminal stage attempt creates a redacted `stage_execution_evidence`
artifact. Every terminal flow creates a `pipeline_execution_receipt` artifact.
The receipt records Prefect IDs, Ops DB IDs, source/environment identity,
verified inputs and outputs, and all stage results.

## Consequences

- Prefect state can be rebuilt or reconciled without changing analytical truth.
- Retry does not create silent duplicate scientific outputs.
- Logs are useful to humans but are never parsed as machine contracts.
- Secrets are represented by names only and are redacted before evidence upload.
- PostgreSQL stores operational state; ArtifactManifestV3 remains immutable truth.
