# Declarative Flow Catalog — Phase 6B

The Stage Registry defines one independently testable command. The Flow Catalog
defines governed multi-stage DAGs by referencing those stable stage IDs.

```text
config/platform/stages.yaml
        │ stage command, risk, ports, resources, gate
        ▼
config/platform/flows.yaml
        │ node references, explicit edges, flow inputs/outputs,
        │ work queues, execution mode and approval boundaries
        ▼
config/platform/generated/flow_catalog.lock.json
```

The catalog does not execute work. Phase 6C will consume the lock through the
Stage Execution Engine and Ops bridge; Phase 6D will materialize Prefect flows
and deployments.

## Catalog coverage

Nine executable flow boundaries cover all 36 non-legacy Stage Registry stages:

| Flow | Stage boundary | Flow queue | Approval policies | Terminal gate |
|---|---|---|---|---|
| `train_model_release` | raw data → trained model → model-ready audit | `cpu-heavy` | `EXPENSIVE` | `MODEL_READY` |
| `register_verified_training_release` | trained-model artifact → MLflow receipt | `release` | none | `MLFLOW_MODEL_REGISTERED` |
| `build_xai_release` | model/XAI → quality → Explanation IR | `cpu-heavy` | `EXPENSIVE` | `EXPLANATION_IR_READY` |
| `build_evidence_release` | Explanation IR → evidence → evaluation subset | `verification` | none | `EVALUATION_SUBSET_READY` |
| `generate_llm_batch` | provider generation → canonicalization → narrative contract | `provider-llm` | `PROVIDER` | `NARRATIVE_CONTRACT_READY` |
| `build_claim_measurement_release` | extraction → finalization → validation → release | `provider-llm` | `PROVIDER`, `EXPENSIVE`, `RELEASE` | `CLAIM_MEASUREMENT_RELEASE_READY` |
| `build_analytical_release` | data mart → metrics/statistics → report/baseline | `release` | `EXPENSIVE`, `RELEASE` | `BASELINE_COMPARISON_READY` |
| `build_visualization_release` | report/baseline → visualization-data-v2 | `release` | `RELEASE` | `VISUALIZATION_DATA_V2_READY` |
| `certify_dashboard_release` | visualization release → bilingual certification | `release` | `RELEASE` | `DASHBOARD_I18N_CERTIFIED` |

`register_verified_training_release` is optional because MLflow is the model
lifecycle surface rather than the scientific source of truth. When invoked, it
must still produce the immutable receipt defined by Phase 5.

## Validation rules

The catalog fails closed when:

- a stage ID is unknown or legacy;
- an optional Stage Registry stage is represented as mandatory;
- an edge references a missing node or port;
- producer and consumer artifact contracts differ;
- a required stage input has zero or multiple sources;
- a required output is neither consumed nor exposed;
- the graph contains a cycle;
- provider, expensive, or release approval declarations are incomplete;
- node or flow work queues conflict with Stage Registry risk policy;
- terminal gates are unknown or not emitted by an exposed output node;
- the recorded Stage Registry hash is stale;
- any active or optional stage is absent from every executable flow.

Optional branches are explicit:

```text
llm.filter_deepseek
  condition: enable_deepseek_compatibility

calibration.prepare / calibration.evaluate
  condition: enable_human_calibration

ops.mlflow_register
  condition: enable_mlflow_registration
```

## Deferred composite boundaries

`verify_source_environment` and `build_complete_release_bundle` remain deferred
to Phase 6D. The current Stage Registry has no dedicated executable stage for
either boundary. Phase 6B does not invent a fake command or misleading success
gate merely to make the names appear complete.

## Commands

```bash
python3 -m research.python.researchops.orchestration.flow_catalog validate
python3 -m research.python.researchops.orchestration.flow_catalog coverage
python3 -m research.python.researchops.orchestration.flow_catalog compile
python3 -m research.python.researchops.orchestration.flow_catalog compile --check
python3 -m research.python.researchops.orchestration.flow_catalog list
python3 -m research.python.researchops.orchestration.flow_catalog show train_model_release
python3 -m research.python.researchops.orchestration.flow_catalog \
  graph train_model_release --format mermaid
```

The generated lock records both `catalog_sha256` and the exact
`stage_registry_sha256`. A flow run in Phase 6C must record both hashes.
