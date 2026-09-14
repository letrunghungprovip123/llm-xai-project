# Scientific Flow Contract Closure — Phase 6F

Phase 6F separates command/output execution success from scientific quality.

- `STAGE_EXECUTION_SUCCEEDED` means the command exited successfully and all declared outputs were registered and verified.
- `verification.success_gate` remains the semantic gate declared by the Flow Catalog, but it is not inferred from file existence.
- `verification.adapter_id`, `report_glob`, and `failure_evidence_globs` define the input for Phase 7 validator adapters.
- Output discovery supports either one `discovery_glob` or an ordered `discovery_globs` collection.
- Early data pipeline CLIs return non-zero when their canonical summary reports are blocked.

The generated `scientific_stage_contracts_v1.json` is the auditable 40-stage matrix used by deterministic contract tests.
