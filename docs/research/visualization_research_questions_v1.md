# Visualization Research Questions v1

Status: `FROZEN_FOR_DASHBOARD_V2`
Parent analytical release: `thesis-report-v1`

The dashboard is a certified presentation layer. It does not redefine metrics,
rerun validators, or use filtered browser state to create new inferential
results.

## RQ1 — Primary operational effectiveness

How do narrative model, controlled evidence condition, and their interaction
affect end-to-end operational faithfulness across all 648 planned LLM
generations?

Primary unit: canonical case with repeated model and evidence conditions.
Primary metric: end-to-end operational faithfulness yield. Unusable generations
remain in the denominator with the frozen zero operational penalty.

## RQ2 — Conditional quality and structured missingness

Among the 638 usable generations, how do conservative faithfulness,
verifiability, and resolved faithfulness differ, and are conclusions robust to
the ten structured S4 failures?

Conditional missing values are not imputed. The dashboard must expose observed
and excluded paired-case counts and the 27-case complete-case sensitivity.

## RQ3 — Evidence utilization and mechanisms

Which evidence exposure, narrative policy, and claim mechanisms are associated
with performance variation across models, evidence conditions, and case
strata?

This RQ uses evidence packages, evidence items, generation structure and policy
metrics, claim status composition, and case metadata. These are descriptive and
mechanistic associations, not causal effects.

## RQ4 — Deployment trade-offs

What quality, reliability, and efficiency trade-offs distinguish the 18 LLM
model-evidence options, and which options are preferred under the five frozen
deployment priorities?

Utility remains a preference-based decision score. User-edited What-if weights
must be labeled exploratory and must never be presented as statistical
significance or probability.

## RQ5 — Measurement robustness

How sensitive are principal findings to the selected claim-measurement artifact
release?

Candidate remains the primary artifact release and V4 remains sensitivity only.
The dashboard must present material Candidate-V4 dependence without claiming
that either artifact is human ground truth.

## RQ6 — Deterministic Template Baseline extension

Compared with a deterministic non-LLM template under the same controlled
evidence, what incremental informational value do LLM narratives provide, and
what reliability and structural-efficiency costs accompany that value?

The Template Baseline has a separate denominator of 216 and is never treated as
a fourth LLM or added to the 648-generation denominator. It is excluded from
all decision rankings. Its structured output is atomized through a deterministic
`STRUCTURED_TEMPLATE_ADAPTER`; this is reproducible but is not identical to the
LLM claim-extraction channel. Human naturalness, usefulness, and trust are not
measured. Zero-millisecond template latency is treated as a measurement-floor
limitation rather than exact physical latency.

## Dashboard narrative order

1. RQ1 establishes the main operational result.
2. RQ2 separates conditional semantic quality from pipeline reliability.
3. RQ3 explains evidence utilization and failure mechanisms.
4. RQ4 turns certified measurements into explicit deployment trade-offs.
5. RQ5 exposes measurement-artifact dependence.
6. RQ6 compares LLM outputs with the deterministic Template Baseline.

The six RQs are the maximum research-question set. Case heterogeneity, policy
compliance, safe-phrase overlap, cost, latency, and reproducibility are analysis
dimensions or supporting evidence, not additional standalone RQs.
