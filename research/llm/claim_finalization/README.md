# Claim finalization

This stage converts stored claim-extraction responses into the frozen claim artifact used by validation.

It never calls a provider and never edits extraction outputs in place. It:

1. replays the latest usable stored response for every successful canonical generation;
2. applies deterministic, versioned normalization rules;
3. rebuilds semantic signatures, claim IDs and local indexes;
4. writes a final claims artifact, a per-claim change log and a manifest with input/output hashes;
5. classifies explicit policy-absence distributed-evidence notes as non-claim-bearing coverage slots;
6. detects every explicit evidence/group count phrase, canonicalizes it into one atomic numeric claim, and fails the run if count completeness is not exact.

Run through `llm:claims-finalize`.


Policy v2 recognizes selected-evidence counts, concept-group counts, mixed-group counts, and factor-member counts across prediction, factor, uncertainty, distributed-evidence, and safe-summary sections.
