# Multi-dataset foundation

This foundation is intentionally additive. It does **not** switch any legacy Home
Credit scientific stage to the new contract yet.

## Boundary

Dataset-specific preparation may vary freely, but it must emit the same canonical
scientific contract:

- dataset identity/version/fingerprint;
- entity/case identity;
- binary target semantics;
- feature matrix;
- feature and concept registries;
- provenance and capabilities.

The common pipeline must not branch on concrete dataset IDs. Future Dataset B/C/D
support is expected to be implemented through dataset-specific preparation adapters.

## Migration safety

1. Keep the legacy Home Credit path operational.
2. Capture/verify the Home Credit baseline before migrating a scientific stage.
3. Migrate one common boundary at a time (split, preprocessing, modeling, XAI, IR).
4. Run Home Credit regression after every boundary.
5. Only then enable Dataset B on that boundary.

## Foundation utilities

```bash
python scripts/multidataset/verify_home_credit_baseline.py
python scripts/multidataset/build_home_credit_canonical_bundle.py
python -m pytest -q tests/research/python/datasets/test_multidataset_foundation.py
```

`DatasetExecutionContext` creates isolated run workspaces under:

```text
.researchops/workspaces/<dataset_id>/<experiment_id>/<run_id>/
```

Existing legacy stages still use their historical paths until deliberately migrated.
