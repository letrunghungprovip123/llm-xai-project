# Unified Gate Contract and Persistence — Phase 7A

`gate_evaluations` is immutable history. `gate_results` is the current operational projection for one `(gate_id, scope_type, scope_id)` identity.

A scientific evaluation has only `PASSED` or `FAILED` outcomes. `PENDING` means no current evaluation and `WAIVED` is a policy-layer effective status introduced by Phase 7C; neither mutates source evidence.

Evaluation identity binds gate/scope, adapter version, policy version, source artifact manifest, evidence artifact manifest, and source evaluation IDs. Reusing the same identity with different normalized semantics fails closed as identity drift.
