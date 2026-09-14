# Platform contracts

`config/platform/` contains Git-managed machine-readable definitions for the
ResearchOps control plane. These files define identity, lifecycle, gate and
artifact vocabulary. They are definitions, not mutable runtime state.

Validate them with:

```bash
python3 -m research.python.researchops.contracts validate
```

Runtime systems must record the canonical contract or registry hash used for a
run. They must not silently edit these definitions in PostgreSQL or a web UI.

## Stage Registry

`stages.yaml` is the human-maintained stage source. The deterministic compiled
representation is `generated/stage_registry.lock.json`.

```bash
python3 -m research.python.researchops.stage_registry compile
python3 -m research.python.researchops.stage_registry validate
```
