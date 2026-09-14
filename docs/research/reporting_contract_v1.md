# Reporting Contract v1

This contract is the wording and denominator guardrail for Chapters 3–6.

## Mandatory terminology

| Use | Do not use |
|---|---|
| risk score / model score | calibrated probability, unless calibration evidence is added |
| operational validator-based faithfulness | ground-truth faithfulness / absolute correctness |
| controlled evidence condition | evidence amount increasing linearly from S0 to S5 |
| association / observed difference | causal effect |
| utility score | probability, accuracy or significance |
| NOT_TESTED | no difference |
| controlled canonical cohort | representative sample of 307,511 records |

## Mandatory denominator notes

- Main LLM experiment: 648 planned generations.
- Conditional semantic analyses: up to 638 usable generations, with exact
  observed denominators shown for every table/test.
- Template Baseline: separate denominator of 216; never added to 648.
- Atomic claims: nested within generations and never independent inferential
  units.

## Required limitations paragraph

The experiment uses 36 purposively selected canonical cases and one generation
per model–evidence condition. Findings are conditional on the frozen dataset,
predictor, prompts, evidence contracts, ontology and deterministic validator.
The absence of blinded human calibration means the reported faithfulness is an
operational measurement rather than an absolute human-validated ground truth.
Ten unusable generations are structurally concentrated in S4 and are retained
with a zero operational score in the primary endpoint; conditional semantic
analyses report their reduced denominators separately. The study does not
establish population representativeness, stochastic stability, human-level
quality, causal independence, fairness, recourse or deployment safety.

## Required ethics/fairness paragraph

Credit assessment is a high-impact setting. Faithful explanations can describe
what influenced the frozen model but do not demonstrate that the model is fair,
that protected groups are treated equally, or that an applicant has actionable
recourse. Sensitive attributes and proxy variables may create disparate impact.
The system is therefore a research evaluation pipeline, not an automated lending
decision tool; real deployment would require subgroup audits, governance,
monitoring and human oversight.

## Result-table rules

1. One official validator release per primary table.
2. Candidate and V4 may appear together only in a clearly labeled sensitivity
   table.
3. Every figure/table states metric, aggregation, population and denominator.
4. Abstract, Chapter 1, Chapter 5 and conclusion must use the same certified
   release numbers.
5. Representative examples are illustrative and never quantitative evidence.
