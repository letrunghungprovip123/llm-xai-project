# Patch 0019 — M20B deterministic validation release

Re-verifies every M20A locked input hash, then invokes the repository's active deterministic claim-validation CLI with the Freddie `claims_v3`, canonical generation index and canonical Evidence Packages. No hidden IR or provider execution is introduced.

Acceptance requires exact claim-ID reconciliation, one validation result per finalized claim, 648 generation summaries, zero execution-error records, and only the five v4 semantic statuses. It deliberately does **not** require a high support rate: unsupported, contradicted and not-verifiable are valid experimental outcomes when correctly assigned.

Gate: `FREDDIE_M20_CLAIM_VALIDATION=PASS`.
