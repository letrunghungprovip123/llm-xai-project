# Patch 0006 — Freddie 12-Month Serious-Delinquency Target

## Scientific boundary

Patch 0006 derives target eligibility/outcomes from SFLLD monthly performance. It does **not** select model features, train models, or modify the common M4–M10 scientific core.

## Frozen target

`serious_delinquency_within_12m_v1`: positive when a mortgage reaches 90+ DPD (status `03+`), `RA`, or a protocol-listed serious zero-balance event during scheduled payment months 1–12. Negative requires complete known observation through month 12, or a clean voluntary payoff (`01`) with complete known observation through termination. All other incomplete/ambiguous histories are censored.

## Critical temporal rule

The horizon is anchored to **Origination First Payment Date + Monthly Reporting Period**. Raw `Loan Age` is not used to define study month because Freddie may reset Loan Age after modification. This prevents post-modification months from being misclassified as the original first year.

## Production processing

Performance is streamed in Loan-Identifier order and only one loan state is retained at a time. Quarterly partitions are built independently and then certified by a manifest/receipt. No full 19.7M-row DataFrame is materialized.

## Fail-closed rules

- duplicate `(Loan Identifier, Monthly Reporting Period)` → fail;
- non-increasing reporting period within a loan → fail;
- unknown/blank delinquency inside an otherwise required negative horizon → censor;
- missing internal month → censor;
- left-censored history cannot become a negative;
- positive evidence is conclusive and overrides censoring;
- no `drop_duplicates`, implicit zero fill, target retuning, or raw-Loan-Age fallback.

## Machine-verified 2024 baseline

The verifier independently re-reads all four target partitions and checks their hashes, identities, target/status values and aggregate counts against the frozen source/protocol baseline.
