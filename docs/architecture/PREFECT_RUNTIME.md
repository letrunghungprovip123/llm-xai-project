# Prefect runtime architecture — Phase 6A

Phase 6A adds workflow infrastructure without changing scientific ownership.
Prefect owns scheduling, flow/task state, retries, worker polling, and suspension.
ArtifactManifestV3 remains the analytical source of truth, while
`llm_xai_ops` remains the operational metadata and audit database.

## Local topology

```text
existing PostgreSQL server
└── dedicated database/user: prefect / prefect_app

Redis 7
├── database 0: Prefect messaging/cache
└── database 1: Docket background-service coordination

Prefect 3.7.8
├── migration container
├── API/UI server --no-services :4200
├── background services process
├── idempotent pool/queue bootstrap
└── process worker with health endpoint :9090
```

The API process does not run migrations at startup. Migration is an explicit
one-shot container. Background services use shared Redis Docket coordination so
periodic actions are not duplicated when the topology is later scaled.

## Work policy

```text
researchops-local-process
├── priority 1  release       concurrency 1
├── priority 2  provider-llm  concurrency 1
├── priority 5  cpu-heavy     concurrency 1
└── priority 10 verification  concurrency 4
```

Lower numeric priority is serviced first. Phase 6A creates no schedules and no
provider execution. Flow-level approval boundaries are added in Phase 6E.

## Commands

```bash
python3 -m research.python.researchops.orchestration validate-runtime
python3 -m research.python.researchops.orchestration init-local-env
scripts/researchops/prefect_local.sh up
python3 -m research.python.researchops.orchestration bootstrap-runtime
python3 -m research.python.researchops.orchestration inspect-runtime
bash scripts/researchops/prefect_phase6a_acceptance.sh
```

Local secrets live only in `.env.researchops-prefect.local`, are mode `0600`,
and are ignored by Git.

## Flow Catalog boundary

Phase 6B adds `config/platform/flows.yaml` as the governed multi-stage DAG
contract. It references Stage Registry IDs and never copies stage commands,
timeouts, resources, secrets, or verification gates. The catalog validates
artifact ports, approval policies, work queues, cycle freedom, and complete
coverage of all active and optional stages.

```bash
python3 -m research.python.researchops.orchestration.flow_catalog validate
python3 -m research.python.researchops.orchestration.flow_catalog coverage
python3 -m research.python.researchops.orchestration.flow_catalog compile --check
```
