# Multi-dataset Common ML v1

Patch 0002 adds an opt-in dataset-neutral path for scientific stages M4–M6 while preserving the legacy Home Credit Batch D/E/F entrypoints.

## Boundary

Dataset-specific preparation emits `DatasetProfileV1` + `CanonicalDatasetBundleV1`.
The common ML path then normalizes source-specific identity and target semantics to:

- `case_id`
- `source_entity_id`
- the profile's canonical target name (currently `target` for Home Credit v1)

No Home Credit source identifier (`SK_ID_CURR`, `SK_ID_BUREAU`, `SK_ID_PREV`) is required by `research/python/common_ml`.

## Stages

1. **M4 common split**
   - verifies canonical bundle artifact hashes
   - maps source target values to canonical binary `{0,1}`
   - creates dataset-scoped `case_id`
   - keeps the existing 70/15/15 stratified policy with seed 42
   - copies semantic registries into the isolated run workspace

2. **M5 common preprocessing**
   - consumes model-feature metadata rather than dataset names
   - reuses the existing preprocessing transformations
   - fits train only and transforms validation/test
   - emits tree and linear branches inside the isolated workspace

3. **M6 common modeling**
   - keeps the same primary model portfolio: Logistic Regression, Random Forest, HistGradientBoosting
   - keeps selection policy: Average Precision → ROC-AUC → lower Brier
   - emits dataset-aware model bundles, predictions, registry and manifest

4. **M7a XAI resolver foundation**
   - resolves tree-first vs model-agnostic SHAP strategy from selected-model capability
   - legacy `load_model_bundle()` remains strict HGB/tree by default
   - multi-dataset callers must explicitly opt out of that historical winner assertion

## Safety

The new path is opt-in. Existing commands are not redirected.
Legacy Home Credit artifacts and release contracts are not rewritten.

## Example

```bash
python scripts/multidataset/run_common_ml.py \
  --dataset-profile config/research/datasets/home_credit_v1.json \
  --canonical-bundle data/manifests/canonical_dataset_bundle_home_credit_v1.json \
  --artifact-root /Users/hung123/Documents/NghienCuuSau/llm-xai-next \
  --experiment-id home_credit_common_ml_v1 \
  --run-id hc-common-ml-smoke-001 \
  --through split
```

Use `--through preprocessing` or `--through modeling` only after the preceding stage passes.
