# ADR-011 — MLflow 3 Logged Model identity

## Status

Accepted for the Phase 5 closure checkpoint.

## Context

MLflow 3 separates a run artifact path from a Logged Model identity. A fitted
model logged by `mlflow.sklearn.log_model()` receives a model ID and the
canonical URI `models:/m-...`. Constructing `runs:/<run_id>/model` is not a
valid substitute when the model bytes are stored by the MLflow 3 Logged Model
service.

Earlier Phase 5 retries created historical registry versions whose source used
`runs:/...`. Those records are retained as audit history and tagged
`SUPERSEDED_SOURCE_URI`; they are not mutated or deleted.

## Decision

- Every newly tracked model must use `models:/m-...`.
- The adapter obtains the model ID from MLflow's `ModelInfo`, or resolves the
  Logged Model by source run and artifact name.
- Failure to obtain a model ID is fail-closed.
- Historical receipts may deserialize `runs:/...` so old evidence remains
  readable, but new tracking and registry writes reject it.
- Registry reconciliation compares the latest immutable receipt and active
  canonical versions; superseded URI records remain visible for audit.

## Consequences

Load-by-version and load-by-alias resolve the same MLflow model bytes. Retry
logic can migrate a historical source by creating a new canonical version
without rewriting prior versions.
