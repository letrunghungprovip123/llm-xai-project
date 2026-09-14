# ADR-012 — Immutable MLflow registration receipt

## Status

Accepted for the Phase 5 closure checkpoint.

## Context

The source `trained_model` artifact is immutable and therefore cannot be
edited after MLflow creates run IDs, Logged Model IDs, registry versions, or
aliases. Keeping those identities only in mutable MLflow/PostgreSQL state would
break the certified artifact lineage.

## Decision

A successful registration publishes an
`mlflow_registration_receipt_v1` ArtifactManifestV3 package. The receipt links:

- source artifact ID and manifest SHA-256;
- experiment and parent/child run IDs;
- canonical Logged Model URIs;
- registered-model versions and the candidate alias;
- MLflow and tracking-contract versions.

The receipt is hash verified, registered in the operations database, linked to
its source artifact, and never edited. An identical retry reuses the existing
receipt. A changed but valid registration produces a new immutable receipt
revision; reconciliation uses the latest receipt for current alias checks while
preserving older evidence.
