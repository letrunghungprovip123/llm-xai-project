# Patch 0024 — M23A Freddie statistical protocol and bootstrap

This patch freezes the three within-case omnibus effects and exactly 33 planned
paired contrasts before final Freddie inference.  S0–S5 remain categorical.
It generalizes statistical validation so legacy Home Credit keeps its S4
missingness check while Freddie supplies the exact unusable generation IDs
frozen by M21.  A deterministic 10,000-iteration percentile bootstrap resamples
canonical cases as complete 18-condition blocks; it is used for effect
uncertainty, not as a replacement p-value.
