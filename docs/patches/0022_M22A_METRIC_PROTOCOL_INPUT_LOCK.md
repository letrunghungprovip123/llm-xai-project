# Patch 0022 — M22A Freddie metric protocol and input lock

The existing metric formula engine is retained.  This patch only parameterizes
input paths and expected cohort counts so Freddie can consume the certified M21
mart without changing Home Credit defaults.  It freezes the formula/denominator
contract before M22 execution and explicitly disables monetary cost comparison
because self-hosted infrastructure cost is incomplete.
