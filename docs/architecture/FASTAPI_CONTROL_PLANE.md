# FastAPI ResearchOps Control Plane

The control plane is the only HTTP application boundary over the ResearchOps
Ops database, immutable artifact store, Prefect and MLflow. Frontends must not
query these systems directly. The Python domain services remain canonical;
routers never reproduce gate, waiver, approval, promotion, artifact or
orchestration rules.

## Architecture boundary

```text
Next.js / CLI / automation
            │ OpenAPI v1
            ▼
FastAPI control plane
  ├── explicit API DTOs and query services
  ├── authentication / RBAC / request context
  ├── API idempotency and durable operations
  ├── existing ResearchOps domain services
  ├── Prefect control gateway
  ├── MLflow read gateway
  └── immutable Artifact Store verification
            │
            ├── PostgreSQL Ops DB
            ├── Prefect
            ├── MLflow
            └── Filesystem / MinIO / S3
```

FastAPI is not a scientific compute plane. Long-running scientific commands and
external mutations are submitted to governed Prefect deployments. SQLAlchemy
sessions are never held open across Prefect, MLflow or object-store network
calls.

## Phase 8A — read-only control plane

Phase 8A exposes governed registries, pipeline and stage runs, artifacts and
lineage, immutable gate history/current gate projections, approvals, releases,
promotion history and MLflow model versions.

Key invariants:

- SQLAlchemy ORM rows are mapped to explicit API DTOs; they are never serialized directly.
- Object-store URIs, credentials and filesystem paths are not returned to clients.
- `GateEvaluation.outcome` and `GateResult.effective_status` remain distinct.
- Cursor pagination is HMAC-protected, fixed-length decoded and bound to resource filters.
- `/healthz` is process liveness; `/readyz` distinguishes critical and degraded dependencies.
- Local authentication is rejected outside local/test environments.
- OpenAPI is generated and hash-locked under `config/platform/generated/`.
- Case Lab and human-review endpoints are intentionally deferred to their own phases.

## Phase 8B — controlled mutations

Phase 8B adds authenticated and authorized mutations with request idempotency,
optimistic preconditions, audit events and durable control-operation records.

### Roles

| Action | Required role |
|---|---|
| Read | `viewer` |
| Trigger/cancel/retry flow | `operator` |
| Approve/reject | `approver` |
| Grant/revoke waiver | `approver` |
| Artifact verification/re-evaluation | `operator` |
| Model/release promotion | `release-manager` |

Shared environments must use JWT/OIDC mode. Hiding controls in a frontend never
replaces server-side RBAC.

### API idempotency

`api_idempotency_requests` namespaces a key by principal, method and route
pattern. The canonical request SHA-256 is stored with the response:

```text
same actor + route + key + payload  → replay original response
same actor + route + key + drift    → 409 STATE_CONFLICT
```

The replay lookup occurs before mutable-state preconditions. A client that lost
a response can therefore retry after the underlying run/release/approval has
already transitioned and still receive the original operation/result.

### Durable control operations

`control_operations` records external and asynchronous actions:

```text
PENDING → RUNNING → SUCCEEDED
                  → FAILED
                  → FAILED_PARTIAL
                  → CANCELLED
```

Operations bind API request IDs, idempotency requests, Prefect flow runs,
pipeline runs and promotion decisions. GET operation endpoints reconcile the
current Prefect/Ops/promotion state without inventing a second workflow truth.

### Run controls

- Trigger validates the governed Flow Catalog and verifies immutable artifact inputs before submission.
- Cancellation requires a non-terminal expected state and a Prefect flow binding.
- Retry is allowed only for `FAILED`/`CANCELLED` runs with the immutable original input/parameter snapshot.
- A failed run must contain at least one failed stage classified `retryable=true`.
- Input or parameter drift is rejected instead of silently creating a different scientific run.

### Approval and waiver controls

Approval decisions enforce expected state, expiry and separation of duties.
Waivers are bound to the exact current gate evaluation, governed policy and
approval. Re-evaluation invalidates stale waiver applicability; the immutable
failed evaluation is never rewritten as passed.

### Artifact controls

Clients cannot submit arbitrary gate outcomes. Re-evaluation resolves the
artifact's governed producer stage, declared output contract and adapter, then
reads only the verified artifact package. Artifact verification uses the
registered manifest; caller-provided hashes are only optimistic preconditions.

### Promotion operations

Model and release promotion are two official governed flows:

```text
promote_model_version
promote_research_release
```

They correspond to `ops.model_promote` and `ops.release_promote`, run on the
`release` queue and produce immutable promotion receipt artifacts. The API
performs a fail-closed preflight (policy hash, lifecycle, required gates,
approval, candidate alias and source-manifest verification), then the worker
checks all invariants again at execution time. MLflow side effects remain under
the Phase 7 promotion saga and can surface `FAILED_PARTIAL` for reconciliation.

## HTTP mutation surface

```text
POST /api/v1/runs
POST /api/v1/runs/{run_id}/cancel
POST /api/v1/runs/{run_id}/retry
POST /api/v1/approvals/{approval_id}/approve
POST /api/v1/approvals/{approval_id}/reject
POST /api/v1/gates/{gate_result_id}/waivers
POST /api/v1/waivers/{waiver_id}/revoke
POST /api/v1/artifacts/{artifact_id}/verifications
POST /api/v1/artifacts/{artifact_id}/evaluations
POST /api/v1/releases/{release_id}/promotions
POST /api/v1/models/{model_name}/versions/{version}/promotions
GET  /api/v1/operations
GET  /api/v1/operations/{operation_id}
```

There is deliberately no generic `POST /gates/evaluate` and no arbitrary
`POST /releases`. Scientific gate outcomes and release identities must remain
derived from governed immutable artifacts.

## Governed counts after Phase 8B

```text
42 Stage Registry stages
15 executable flows
15 manual-only Prefect deployments
```

## Acceptance

```text
FASTAPI_READ_MODEL=PASS
OPENAPI_READ_CONTRACT=PASS
API_MUTATION_IDEMPOTENCY=PASS
API_OPTIMISTIC_CONCURRENCY=PASS
API_AUDIT_TRAIL=PASS
ASYNC_RUN_CONTROL=PASS
MODEL_PROMOTION_OPERATION=PASS
RELEASE_PROMOTION_OPERATION=PASS
PROMOTION_OPERATION_RECONCILIATION=PASS
RESEARCHOPS_CONTROL_PLANE_LIVE_ACCEPTANCE=PASS
RESEARCHOPS_PHASE8_CONTROL_PLANE=COMPLETE
```
