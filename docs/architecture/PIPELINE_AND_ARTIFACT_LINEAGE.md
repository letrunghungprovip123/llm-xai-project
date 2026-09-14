# Pipeline and artifact lineage

The active pipeline is a directed sequence of explicit producers and immutable
outputs. Phase 1 freezes vocabulary; Phase 2 introduces a machine-readable Stage
Registry containing the exact commands, inputs, outputs, risks and success gates.

## Major boundaries

```text
raw data
→ audited data context
→ feature matrix and split
→ trained model and model metrics
→ XAI artifacts and quality report
→ Explanation IR
→ evidence packages and evaluation subset
→ raw and canonical LLM generations
→ atomic and finalized claims
→ claim validation release
→ data mart and analytical mart
→ statistics, diagnostics and decision support
→ thesis report release
→ baseline comparison
→ visualization release
→ dashboard certification
```

Every official artifact must eventually identify:

- artifact type and schema version;
- producer stage and producer run;
- source commit and environment snapshot;
- parent artifacts;
- files, byte sizes, counts and SHA-256 hashes;
- declared scientific limitations.

Operational indexes may point to artifacts, but only the manifest plus verified
object bytes defines artifact identity.
