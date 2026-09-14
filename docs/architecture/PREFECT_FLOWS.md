# Prefect official flows and deployments

Phase 6D exposes every executable Flow Catalog definition through a thin Prefect
flow entrypoint. The generic engine validates artifact inputs, creates or reuses an
Ops DB pipeline run, executes enabled nodes in topological order, verifies outputs,
and publishes an immutable `pipeline_execution_receipt`.

## Deterministic configuration

```bash
python3 -m research.python.researchops.orchestration.flow_catalog validate
python3 -m research.python.researchops.orchestration.prefect_adapter.deployment_cli validate
python3 -m research.python.researchops.orchestration.prefect_adapter.deployment_cli compile-check
```

Deployments are intentionally manual-only. The checked-in catalog maps all flows to
`researchops-local-process` and one of `verification`, `cpu-heavy`, `provider-llm`,
or `release`. No default schedule exists.

## Acceptance fixtures

`prefect_acceptance_fixture` exercises success, idempotent reuse, retryable exit
codes, fail-closed output discovery, and cancellation without changing scientific
artifacts. `prefect_approval_acceptance_fixture` is protected and is completed by
the approval boundary introduced in Phase 6E.

## Import-safe deployment entrypoints

The deployment catalog uses fully qualified Python module entrypoints such as
`research.python.researchops.orchestration.prefect_adapter.flows.train_model_release`.
Prefect must import the flow as part of its package so that relative imports inside
the orchestration package keep their package context. File-path entrypoints are
still accepted by the contract for external flows, but they are not used for the
official ResearchOps deployments.

Before `prefect deploy --all`, the bootstrap service loads every configured flow
through Prefect's own entrypoint loader. Any import error, flow-name mismatch, or
missing module fails the deployment before the catalog is registered. This live
preflight complements the deterministic static symbol check used by CI and local
contract tests.

## Ops database connectivity boundary

The process worker must not reuse the host-facing operational database URL because
`127.0.0.1:5433` resolves inside the worker container. The worker accepts an
optional `RESEARCHOPS_INTERNAL_DATABASE_URL`; otherwise its entrypoint derives a
container-network URL from the same `RESEARCHOPS_POSTGRES_*` credentials used to
initialize the existing Ops database. Before the Prefect worker starts accepting
runs, it executes a redacted `SELECT 1` preflight. A credential or network mismatch
therefore fails the worker closed and cannot produce a Prefect run without its
authoritative Ops binding.


## Worker concurrency bootstrap

The worker concurrency limit is propagated explicitly through Compose and defaults
to the runtime-contract value `4`. The worker entrypoint independently applies the
same default and rejects zero or non-numeric values before database preflight or
worker startup. Moving worker startup behind a shell entrypoint must therefore not
lose the default that was previously expanded directly inside the Compose command.


## Prefect retry-delay compatibility

Stage retry backoff is converted at the Prefect adapter boundary to a concrete
`list[int]` (`[5, 10, ...]`). Prefect 3.7.8 rejects tuples for
`retry_delay_seconds`, so immutable internal collection conventions must not leak
into `Task.with_options`. Stages with zero retries pass `None`; retry eligibility
continues to be controlled independently by `prefect_retry_condition`.
