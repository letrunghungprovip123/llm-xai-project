# ResearchOps Artifact Platform

## Boundary

Git owns definitions. Artifact manifests and their referenced bytes own immutable
research outputs. PostgreSQL, introduced later, only indexes operational state.

## Phase 3A

Phase 3A provides `artifact_manifest_v3`, canonical hashing, a package builder,
an immutable `FilesystemArtifactStore`, verification and CLI commands. It does
not introduce MinIO, S3, PostgreSQL, Prefect or MLflow.

## Package layout

```text
<store-root>/<artifact-type>/<schema-version>/<artifact-id>/
├── manifest.json
└── files/
    └── <relative paths>
```

`manifest.json` is written last and acts as the package commit marker. Existing
artifact IDs are immutable. Repeating an identical put is idempotent; attempting
to reuse an ID for different content is rejected.

## Commands

```bash
python3 -m research.python.researchops.artifacts validate-manifest path/manifest.json
python3 -m research.python.researchops.artifacts inspect <artifact-id>
python3 -m research.python.researchops.artifacts verify <artifact-id>
```

## Phase 3B

`S3ArtifactStore` implements the same immutable package contract for Amazon S3
and MinIO. Data objects are uploaded first and `manifest.json` is uploaded last.
The local MinIO service is opt-in:

```bash
set -a
source config/platform/researchops.env.example
set +a
docker compose --profile researchops-storage up -d researchops-minio
python3 -m research.python.researchops.artifacts bootstrap-s3
```

Copy the example values to a private `.env`; do not use the example password in
a shared environment.

A `ReleasePointer` maps a human release ID to an immutable artifact ID and
manifest hash. `CertifiedReleaseResolver` downloads and verifies the package,
installs it into a hash-keyed cache, and can run the existing Dash release guard
through an injected acceptance callback. It never falls back to unverified
files.
