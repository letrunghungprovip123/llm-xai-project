# Change management

## Change classes

1. **Behavior fix:** changes runtime behavior without changing an analytical contract.
2. **Contract change:** changes schema, identity, lifecycle, gate or route composition.
3. **Analytical change:** changes metrics, denominators, inference or source artifacts.
4. **Operational change:** changes orchestration, storage, database or deployment.
5. **Documentation-only change:** explains existing accepted behavior.

## Required sequence

```text
proposal → ADR/contract update → implementation → deterministic tests
→ acceptance evidence → clean commit → release or migration
```

Provider-dependent and expensive stages remain deliberate. Routine pull-request
checks may verify their definitions but must not invoke paid generation.

A frozen migration must never be rewritten after use in a shared environment.
A certified artifact must never be edited in place; create a new artifact or release.
