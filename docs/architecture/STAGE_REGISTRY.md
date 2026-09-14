# Declarative Stage Registry

The Stage Registry is the Git-managed operational map of the active Python and
TypeScript research pipeline.

```text
config/platform/stages.yaml
→ Pydantic validation
→ deterministic lock JSON and SHA-256
→ future Prefect flow/task adapters
```

The registry does not execute provider work by itself. It records command,
inputs, outputs, risk class, approval policy, resources and success gate.

## Commands

```bash
python3 -m research.python.researchops.stage_registry compile
python3 -m research.python.researchops.stage_registry validate
python3 -m research.python.researchops.stage_registry coverage
python3 -m research.python.researchops.stage_registry graph
python3 -m research.python.researchops.stage_registry show llm.generate
python3 -m research.python.researchops.stage_registry verify-command ml.train
```

`stage_registry.lock.json` is deterministic and committed. Runtime systems must
record its `registry_sha256` for every pipeline run.

Secret values never belong in the registry. Only environment-variable names are
listed. Provider and expensive stages declare approval policies and are not run
by routine CI.
