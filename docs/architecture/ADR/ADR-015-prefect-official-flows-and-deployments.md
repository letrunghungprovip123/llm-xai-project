# ADR-015 — Governed Prefect flows and manual-only deployments

## Status

Accepted for ResearchOps Phase 6D.

## Decision

The declarative Flow Catalog remains the source of truth for DAG membership,
stage references, queues, approval boundaries, inputs and outputs. Python flow
functions are intentionally thin named entrypoints that delegate to the generic
catalog execution engine.

Every executable Flow Catalog entry has exactly one checked-in Prefect deployment.
Deployments are manual-only, use the `researchops-local-process` pool, inherit the
catalog queue, and contain no schedule. The generated `prefect.yaml` and deployment
lock are deterministic products of the deployment catalog.

A process worker mounts the repository read-write because accepted scientific
commands already write declared outputs into repository release paths. Inputs and
outputs remain governed by immutable artifact verification; a writable checkout is
not treated as scientific truth.

## Consequences

- Flow structure is not duplicated in Python decorators.
- Provider and release flows cannot start periodically by accident.
- Deployment bootstrap is idempotent and runs before the worker starts.
- Adding a flow requires Stage Registry, Flow Catalog, Python entrypoint and
  deployment-catalog agreement.
