# ResearchOps Operational Database

## Boundary

The `llm_xai_ops` PostgreSQL database stores mutable operational state and a
queryable index of immutable artifacts. It does not store model binaries,
certified CSV/JSONL/Parquet bytes, or recompute analytical truth.

MLflow and Prefect must use separate databases/users and own their migrations.

## Core schema

- environment and code snapshots;
- pipeline and stage runs;
- run events and approvals;
- artifact metadata, files and lineage edges;
- releases and release membership;
- gate results and audit events.

## Local service

```bash
set -a
source config/platform/researchops-db.env.example
set +a
docker compose --profile researchops-db up -d researchops-postgres
python3 -m research.python.researchops.ops_core upgrade
```

All schema changes are delivered through Alembic migrations. GUI schema edits
are not part of the accepted workflow.

## Registration and reconciliation

Artifact registration begins only after object-store verification. The database
transaction inserts the artifact index, files, parent lineage and audit event.
Object storage and PostgreSQL cannot share one ACID transaction, so the platform
uses manifest-last writes, idempotent registration and reconciliation.

```bash
python3 -m research.python.researchops.ops_core reconcile --mode report-only
```

`repair-safe` may register verified orphan artifacts whose parents are already
registered. It never deletes object bytes or rewrites certified manifests.
Release promotion requires recorded blocking gates and, when configured, an
unexpired approval.
