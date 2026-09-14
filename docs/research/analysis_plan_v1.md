# Frozen Analysis Plan v1 — LLM-XAI Thesis

## 1. Primary research estimand

The primary endpoint is **end-to-end operational faithfulness yield** over all
648 planned LLM generations. For a usable generation with at least one
applicable claim, the score equals supported claims divided by applicable
claims. A planned generation that is unusable receives the pre-specified
operational penalty of zero. The endpoint therefore evaluates semantic quality
and pipeline completion jointly.

The unit of inference is the canonical case. Claim rows are never treated as
independent observations.

## 2. Secondary estimands

Resolved faithfulness, verifiability and conservative faithfulness are
conditional semantic metrics. They are calculated only where their denominator
exists and remain missing for unusable generations. Usability is reported as a
separate planned-generation endpoint.

The primary and secondary estimands answer different questions and must not be
substituted after results are observed.

## 3. Statistical plan

The primary 648-row matrix is balanced across 36 cases, three models and six
controlled evidence conditions. The primary omnibus analysis uses a two-factor
within-case repeated-measures ANOVA with Greenhouse–Geisser correction.
Pre-specified post-hoc comparisons are paired by case and corrected with Holm
within each contrast family.

Conditional semantic analyses report complete pair counts and excluded pair
counts. A complete-case factorial sensitivity analysis is run on cases for
which all 18 conditions are usable. Conclusions are compared with the primary
operational analysis; disagreements are reported rather than selected away.

S0–S5 are categorical experimental conditions. S4 is a rich-evidence stress
condition with truncation risk, while S5 adds a structural intervention. No
unplanned linear S0→S5 trend is inferred.

## 4. Validator decision

`claim_measurement_candidate_primary_v1` is the primary operational release
because it is the exact lineage used by the existing certified analytical
chain. V4 remains a sensitivity condition and is not mixed into primary tables.
The V4 release verdict is rejected because its human-calibration gate did not
pass.

This decision establishes one reproducible source of truth; it does **not**
claim that the selected validator is human ground truth. Until real blinded
human calibration is completed, all results are described as operational
faithfulness under the frozen project ontology and deterministic validator.

## 5. Reporting boundaries

- The predictor output is called a **risk score**, not a calibrated probability.
- The 36 cases are a controlled canonical cohort, not a prevalence-representative
  sample of all Home Credit records.
- Repeat count is one; run-to-run stochastic stability is not established.
- Lexical overlap does not establish copying or causal dependence.
- Structured output does not guarantee semantic correctness.
- Utility is a preference score, not probability or significance.
- Template-baseline naturalness, clarity and usefulness require human study.
- Faithfulness does not establish fairness, recourse or deployment safety.
