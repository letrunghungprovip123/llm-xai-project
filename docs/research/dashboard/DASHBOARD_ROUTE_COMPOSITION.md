# Dashboard route composition

`dashboard_contract_v2` froze nine conceptual research sections before the Dash
application was implemented. The completed application intentionally consolidates
those sections into seven physical routes.

| Physical page | Route | Conceptual sections |
|---|---|---|
| Overview | `/` | `executive_overview` |
| Effectiveness | `/effectiveness` | `performance_reliability`, `statistical_evidence` |
| Mechanisms | `/mechanisms` | `mechanisms_diagnostics` |
| Decision | `/decision` | `decision_studio` |
| Robustness | `/robustness` | `validator_sensitivity`, `template_baseline_comparison` |
| Cases | `/cases` | `case_explorer` |
| Methods | `/methods` | `reproducibility` |

The machine-readable source is
`config/research/dashboard_route_composition_v1.json`. Validation requires every
conceptual section exactly once and requires each physical page to inherit the
exact union of RQs and datasets from the mapped conceptual sections.

This composition does not alter analytical definitions. It only records the
post-implementation information architecture.
