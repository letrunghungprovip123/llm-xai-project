# Dashboard Data Contract v2

Status: `FROZEN_BEFORE_DASH_IMPLEMENTATION`

## Purpose

This contract completes the analytical inputs required before Dash UI work.
The dashboard consumes immutable presentation marts and does not recompute the
research pipeline.

## Required execution order

```bash
python3 -m research.python.baseline_comparison.main
python3 -m research.python.visualization_v2.main
python3 -m pytest -q \
  tests/research/python/baseline_comparison \
  tests/research/python/visualization_v2
```

Required gates:

```text
REPORT_WRITING_READY
BASELINE_COMPARISON_READY
VISUALIZATION_DATA_V2_READY
```

## Template Baseline analytical layer

The canonical input contains 216 deterministic template generations: 36 cases
by six evidence conditions. The layer atomizes structured fields using
`structured_template_adapter_v1`, then validates prediction labels, displayed
scores, feature/concept exposure, and direction against frozen case and
evidence contracts.

The adapter is deterministic and auditable, but it is not identical to the LLM
claim-extraction channel. Therefore:

- Template results use a separate 216-generation denominator.
- LLM results retain the frozen 648-generation denominator.
- Comparisons pair by `case_id × evidence_level`.
- Inferential tests use paired canonical cases, never atomic claims.
- S1-S4 pooled tests first average evidence levels within each case.
- Missing conditional LLM scores are not imputed; planned, observed, and
  excluded pair counts are stored explicitly.
- Template Baseline is excluded from all decision rankings.
- Human naturalness, usefulness, trust, and preference are not inferred.
- Zero-millisecond template latency is marked measurement-floor limited.

Generated baseline datasets:

| Dataset | Grain | Expected rows | Purpose |
|---|---|---:|---|
| `baseline_claims.csv` | atomic template claim | data-dependent | deterministic claim audit |
| `baseline_generation_metrics.csv` | template generation | 216 | RQ6 metrics |
| `baseline_option_performance.csv` | evidence condition | 6 | template profile |
| `llm_vs_template_case_pairs.csv` | LLM × case × evidence | 648 | paired comparison |
| `llm_vs_template_summary.csv` | model/context summary | 24 | dashboard summaries |
| `llm_vs_template_tests.csv` | planned paired test | 105 | RQ6 inference |

## Four presentation marts

### `evidence_design_summary.csv`

Grain: 216 case × evidence-condition packages.

It exposes evidence amount, feature/concept composition, coverage, entropy,
adaptive/fixed K, structural guidance, concept grouping, SHAP mass, and policy
requirements. It answers what S0-S5 actually contain instead of treating the
condition label as a black box.

### `evidence_utilization_summary.csv`

Grain: 864 generations: 648 LLM plus 216 Template Baseline.

It connects selected evidence to feature/concept mentions, invalid declarations,
claim outcomes, faithfulness, and dominant validator reason codes. It supports
RQ3 without claiming causal mediation.

### `narrative_structure_summary.csv`

Grain: 864 generations.

It contains length, sentence/factor structure, technical-term density, required
sections, uncertainty/distributed/partial-evidence compliance, and prohibited
wording flags. These are structure and policy measures, not human naturalness.

### `case_heterogeneity_summary.csv`

Grain: 864 generations.

It combines prediction outcome, selection stratum, threshold distance,
complete-case status, evidence condition, quality, claim composition, length,
and latency. It supports systematic case selection and prevents cherry-picking.

## Research questions

The maximum research-question set is frozen at five LLM-core RQs plus one
Template Baseline extension. Additional fields are supporting dimensions rather
than new RQs.

- RQ1: primary operational effectiveness.
- RQ2: conditional quality and structured missingness.
- RQ3: evidence utilization and mechanisms.
- RQ4: deployment trade-offs.
- RQ5: measurement robustness.
- RQ6: deterministic Template Baseline extension.

## Metric visibility

`visualization_metric_visibility_v1.json` separates headline, explanatory,
internal-validation, and disabled metrics. This prevents reciprocal or
complementary metrics from becoming duplicate dashboard findings and blocks
monetary cost, human quality, stochastic stability, and precise template
latency until appropriate inputs exist.

## Final output directory

```text
data/reports/llm_validation/validation_v1/analysis/visualization_v2/
```

The Dash application must read this immutable directory only after
`VISUALIZATION_DATA_V2_READY` passes.

## Certified statistical and robustness presentation datasets

Visualization v2 also copies the frozen statistical and validator-sensitivity
artifacts into the immutable presentation directory. Dash pages must read these
copies rather than traverse back into analytical working directories.

| Dataset | Expected rows | Dashboard purpose |
|---|---:|---|
| `descriptive_statistics.csv` | 272 | distribution summaries and lower-tail context |
| `omnibus_tests.csv` | 3 | primary model, evidence, and interaction effects |
| `paired_tests.csv` | 33 | frozen primary planned contrasts |
| `conditional_paired_tests.csv` | 99 | conditional semantic contrasts with observed/excluded pairs |
| `complete_case_omnibus_tests.csv` | 3 | 27-case balanced sensitivity |
| `statistical_sensitivity_summary.csv` | 3 | primary-versus-complete-case conclusion stability |
| `unusable_generations.csv` | 10 | structured S4 failure evidence |
| `validator_generation_pairs.csv` | 648 | Candidate-V4 paired generations |
| `validator_metric_summary.csv` | 112 | measurement-artifact deltas by scope |
| `validator_sensitivity_tests.csv` | 40 | case-level measurement-robustness tests |
| `certified_report_numbers.csv` | 18 | flattened headline counts, rates, and claim statuses |

The statistical page is read-only. Browser filters may select existing tests,
but must never calculate replacement p-values or redefine correction families.

## Integrity and fail-closed loading

Before generating any baseline or visualization output, the pipeline verifies
SHA-256 and byte-count contracts from `report_release_manifest.json`. The
visualization build also verifies every baseline output listed in
`baseline_comparison_manifest.json`. A missing or modified certified artifact
blocks generation instead of silently falling back to stale data.
