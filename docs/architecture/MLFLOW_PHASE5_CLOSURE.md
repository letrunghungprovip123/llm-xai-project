# MLflow Phase 5 closure and portability

Phase 5 is closed by three independent contracts:

```text
ArtifactManifestV3 training release
        ↓ verified by ID
MLflow 3 Tracking + Logged Models
        ↓ canonical models:/m-... identity
Model Registry + candidate alias
        ↓
Immutable registration receipt
        ↓
Two-way reconciliation
```

## Portable training release

A new `model_training_release_v1` package contains the three joblib bundles,
input examples, feature schemas, a portable model registry, and a normalized
training manifest. Runtime consumers resolve all files inside the downloaded
artifact. They do not follow absolute paths embedded in a historical source
registry.

The packaging command searches only:

1. `<project>/artifacts/models`; or
2. a directory explicitly supplied with `--model-source-dir` for a one-time
   legacy import.

The resulting registry paths are artifact relative:

```text
models/<model>.joblib
schemas/preprocessed_feature_columns_<branch>.json
schemas/preprocessed_feature_mapping_<branch>.json
```

Use:

```bash
python3 -m research.python.researchops.mlflow_tracking \
  verify-training-release-portability \
  --artifact-profile development-minio \
  --artifact-id <artifact-id> \
  --report-path /tmp/training-portability.json
```

## Machine report contract

Commands support `--report-path`. The JSON document is written to a temporary
file, flushed, and atomically renamed. Stdout remains informational and may
contain third-party messages.

## Acceptance paths

- `mlflow_phase5_current_state_acceptance.sh` proves retry safety and clean
  reconciliation for the accepted environment.
- `mlflow_phase5_fresh_state_acceptance.sh` uses a dedicated PostgreSQL
  database, MinIO bucket/user, MLflow server on port 5001, and temporary
  filesystem artifact store. It never resets the current MLflow database,
  ResearchOps database, production artifact bucket, or Docker volumes.
