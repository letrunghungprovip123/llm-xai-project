# Patch 0020 — M21A Freddie analysis contract and input lock

This patch freezes the deterministic M20 release before any Freddie metric or
statistical result is computed.  It adds a dataset-neutral case metadata
adapter so the common mart accepts both legacy Home Credit
`internal_metadata.customer.SK_ID_CURR` and Freddie
`internal_metadata.case.case_id` without silent precedence.

The lock derives, rather than hard-codes, the exact unusable-cell identity and
complete-case count from the 648-row canonical matrix.  It records SHA-256 for
M20 claims/validation/generation artifacts and relevant source bytes.  No
provider, training or SHAP stage is reachable from this patch.

The analysis protocol is explicitly described as retrospectively formalized and
frozen before final Freddie analysis, not as a prospective preregistration.
