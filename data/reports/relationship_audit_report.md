# Relationship Audit Report

Created at: `2026-06-21T11:15:46`

## Relationship Summary

| Relationship | Parent | Child | Join Key | Avg child records | Max child records | Parent without history | Unmatched child keys | Aggregation required |
|---|---|---|---:|---:|---:|---:|---:|---|
| application_train -> bureau | application_train.csv | bureau.csv | SK_ID_CURR | 5.5612 | 116 | 44020 | 42320 | yes |
| bureau -> bureau_balance | bureau.csv | bureau_balance.csv | SK_ID_BUREAU | 31.2257 | 97 | 942074 | 43041 | yes |
| application_train -> previous_application | application_train.csv | previous_application.csv | SK_ID_CURR | 4.8571 | 73 | 16454 | 47800 | yes |
| previous_application -> installments_payments | previous_application.csv | installments_payments.csv | SK_ID_PREV | 12.884 | 293 | 711309 | 38847 | yes |
| previous_application -> POS_CASH_balance | previous_application.csv | POS_CASH_balance.csv | SK_ID_PREV | 10.7473 | 96 | 771311 | 37422 | yes |
| previous_application -> credit_card_balance | previous_application.csv | credit_card_balance.csv | SK_ID_PREV | 29.6712 | 96 | 1577279 | 11372 | yes |

## Main Conclusion

All auxiliary tables are many-to-one or many-to-many relative to `application_train`. Therefore, raw auxiliary tables must not be directly merged into `application_train`. Each auxiliary table must first be aggregated to one row per `SK_ID_CURR` before building the final feature matrix.

## Final Rule

The final feature matrix must contain exactly one row per `SK_ID_CURR`.