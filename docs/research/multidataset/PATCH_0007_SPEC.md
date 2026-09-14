# Patch 0007 — Freddie SFLLD 2024 Preparation Adapter (M12B/C)

## Boundary

Dataset-specific code ends here. The patch consumes the M11 certified raw ZIP and
M12A target receipt/partitions and emits `CanonicalDatasetBundleV1` for the frozen
common M4–M10 pipeline.

## Frozen primary feature policy

Nineteen origination-time predictors are admitted. High-cardinality ZIP/MSA/seller,
identity, constant 2024 fields, all-missing 2024 fields, temporal anchor dates and
all monthly performance fields are excluded from the primary model matrix.

Sentinel/enum normalization is explicit and versioned in
`freddie_sflld_2024_feature_policy_v1.json`; unknown values fail closed.

## Scientific invariants

- only M12A `ELIGIBLE` loans enter canonical artifacts;
- feature and target identities are exactly one-to-one;
- no monthly performance feature enters X;
- target positive/eligible counts equal the certified M12A receipt;
- every model feature has a feature-registry entry and a known concept;
- dataset fingerprint depends on raw bytes, target protocol, feature policy,
  concept registry and adapter source hash, but not machine-specific paths;
- Home Credit and common M4–M10 behavior are unchanged.

## Canonical artifacts

- `data/processed/feature_matrix_full.parquet`
- `data/processed/target_full.parquet`
- `ml/registry/feature_registry.csv`
- `ml/registry/feature_registry.yaml`
- `ml/registry/concept_registry.yaml`
- `data/manifests/canonical_dataset_bundle_freddie_sflld_2024_v1.json`
- `data/manifests/freddie_sflld_2024_preparation_manifest_v1.json`
- `data/manifests/freddie_sflld_2024_m12_preparation_receipt_v1.json`

## Stop conditions

Any upstream hash mismatch, unknown source enum/sentinel, duplicate identity,
feature/target identity mismatch, count mismatch, registry gap or performance
leakage blocks M12. No row or feature is silently coerced to force a PASS.
