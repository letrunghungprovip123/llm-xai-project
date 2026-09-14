# Stage execution engine — Phase 6C

The Stage Execution Engine is the governed bridge between Stage Registry,
Prefect, PostgreSQL Ops DB, and the Artifact Platform.

```text
Prefect task
  -> resolve Stage Registry definition
  -> verify/download immutable inputs
  -> create or reuse Ops stage_run
  -> execute argv with shell=False and an environment allowlist
  -> discover new or changed declared outputs
  -> package, verify, store, and register each output
  -> record the stage gate
  -> upload redacted execution evidence
  -> commit terminal Ops state and immutable events
```

## Machine contracts

- `stage_execution_result_v1`
- `pipeline_execution_receipt_v1`
- `ArtifactManifestV3`

Stdout and stderr are diagnostic evidence only. Stage commands that need to
return structured data must write a declared file or use `--report-path`.

## Identity and retry

Flow and stage identities use SHA-256 over canonical JSON. Inputs include both
artifact ID and manifest SHA-256. Retriable failures are limited to transient
network/provider/rate-limit/infrastructure classes. Schema, hash, corruption,
policy, approval, and command-configuration failures do not retry.

## Security boundary

Child processes receive only safe base variables, stage-declared secret names,
and explicit `RESEARCHOPS_*` orchestration values. `shell=True` is prohibited.
Execution evidence redacts credentials, bearer tokens, and credential-bearing
URLs before storage.
