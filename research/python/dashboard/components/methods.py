"""Research-audit components for Page 7."""

from __future__ import annotations

from collections.abc import Iterable

from dash import dcc, html
import pandas as pd

from ..data.contracts import (
    ReleaseAudit,
    ResearchQuestionRecord,
    ValidationGateRecord,
)
from ..i18n import (
    DEFAULT_LOCALE,
    format_integer,
    format_percent,
    methods_identifier_label,
    normalize_locale,
    reporting_role_label as localized_reporting_role_label,
    t,
    visibility_tier_label,
)
from ..display_labels import (
    display_label,
    gate_state_label,
    research_status_label,
)
from ..ids import (
    METHODS_ARTIFACT_GRID_ID,
    METHODS_DICTIONARY_GRID_ID,
    METHODS_HEADLINE_GRID_ID,
)
from ..settings import (
    METHODS_VISIBILITY_TIER_DESCRIPTIONS,
    METHODS_VISIBILITY_TIER_LABELS,
    METHODS_VISIBILITY_TIER_ORDER,
)
from .data_grid import data_grid


def humanize_identifier(value: object) -> str:
    """Backward-compatible wrapper over the curated display-label registry."""

    return display_label(value)



def _format_certified_value(row: pd.Series, locale: object = DEFAULT_LOCALE) -> str:
    value = float(row["value"])
    if str(row["value_type"]) == "rate":
        return format_percent(locale, value, decimals=2)
    return format_integer(locale, int(round(value)))


def methods_context_header(
    audit: ReleaseAudit,
    *,
    passed_gates: int,
    gate_count: int,
    locale: object = DEFAULT_LOCALE,
):
    return html.Div(
        [
            html.Span(
                t(
                    locale,
                    "methods.context.line",
                    datasets=audit.dataset_count,
                    passed=passed_gates,
                    total=gate_count,
                )
            ),
            html.Div(
                [
                    html.Span("Certified presentation layer", className="methods-badge methods-badge--ready"),
                    html.Span("Read-only over frozen outputs", className="methods-badge"),
                ],
                className="methods-badge-row",
            ),
        ],
        className="methods-context-line",
    )


def release_identity_card(audit: ReleaseAudit):
    facts = [
        ("Presentation release", audit.visualization_release_id),
        ("Parent analytical release", audit.analytical_release_id),
        ("Source commit", audit.short_commit),
        ("Git branch", audit.parent_git_branch),
        ("Source-tree SHA-256", f"{audit.short_tree_sha}…"),
        ("Verified analytical artifacts", f"{audit.verified_parent_artifact_count:,}"),
        ("Verified Template artifacts", f"{audit.verified_baseline_artifact_count:,}"),
        ("Certified datasets", f"{audit.dataset_count:,}"),
    ]
    return html.Section(
        [
            html.Div(
                [
                    html.Div("Certified release identity", className="methods-eyebrow"),
                    html.H2("Verified for certified presentation"),
                    html.P(
                        "The application renders immutable presentation marts from the frozen analytical release."
                    ),
                ],
                className="methods-release-hero__intro",
            ),
            html.Dl(
                [
                    html.Div([html.Dt(label), html.Dd(value)])
                    for label, value in facts
                ],
                className="methods-release-facts",
            ),
            html.Details(
                [
                    html.Summary("View full lineage identifiers"),
                    html.Div(
                        [
                            html.Div([html.Strong("Full source commit"), html.Code(audit.parent_git_commit)]),
                            html.Div([html.Strong("Full source-tree SHA-256"), html.Code(audit.source_tree_sha256)]),
                            html.Div([html.Strong("Parent release ID"), html.Code(audit.parent_release_id)]),
                        ],
                        className="methods-lineage-identifiers",
                    ),
                ],
                className="methods-details methods-details--compact",
            ),
        ],
        className="methods-release-hero",
    )


def release_lineage(gates: Iterable[ValidationGateRecord]):
    nodes = []
    for index, gate in enumerate(gates, start=1):
        state = "ready" if gate.passed else "blocked"
        nodes.append(
            html.Li(
                [
                    html.Span(str(index), className=f"methods-lineage-node__dot methods-lineage-node__dot--{state}"),
                    html.Div(
                        [
                            html.Strong(gate.layer_label),
                            html.Span(
                                gate_state_label(gate.passed),
                                className=f"methods-status methods-status--{state}",
                                title=f"Technical gate: {gate.exit_gate}",
                            ),
                            html.Small(gate.meaning),
                        ]
                    ),
                ],
                className="methods-lineage-node",
                **{"data-gate-id": gate.layer_id},
            )
        )
    nodes.append(
        html.Li(
            [
                html.Span(str(len(nodes) + 1), className="methods-lineage-node__dot methods-lineage-node__dot--ready"),
                html.Div(
                    [
                        html.Strong("Dash application"),
                        html.Span("Read-only", className="methods-status methods-status--ready"),
                        html.Small("Browser state selects certified outputs and never recomputes inference."),
                    ]
                ),
            ],
            className="methods-lineage-node",
            **{"data-gate-id": "dash_application"},
        )
    )
    return html.Section(
        [
            html.Div([html.H2("Release lineage"), html.P("Frozen analytical artifacts flow into a verified presentation release.")], className="methods-section-heading"),
            html.Ol(nodes, className="methods-lineage"),
        ],
        className="methods-card",
    )


def validation_gate_matrix(gates: Iterable[ValidationGateRecord]):
    rows = []
    for gate in gates:
        state = "ready" if gate.passed else "blocked"
        checks = "—" if gate.check_count is None else f"{gate.check_count:,}"
        failed = "—" if gate.failed_check_count is None else f"{gate.failed_check_count:,}"
        rows.append(
            html.Details(
                [
                    html.Summary(
                        [
                            html.Span(gate.layer_label, className="methods-gate-row__label"),
                            html.Span(
                                gate_state_label(gate.passed),
                                className=f"methods-status methods-status--{state}",
                                title=f"Technical gate: {gate.exit_gate}",
                            ),
                            html.Span(checks, className="methods-gate-row__count"),
                            html.Span(failed, className="methods-gate-row__count"),
                            html.Span(gate.source_artifact, className="methods-gate-row__source"),
                        ]
                    ),
                    html.Div(
                        [
                            html.P(gate.meaning),
                            html.Dl(
                                [
                                    html.Div([html.Dt("Expected technical gate"), html.Dd(html.Code(gate.expected_gate))]),
                                    html.Div([html.Dt("Observed technical gate"), html.Dd(html.Code(gate.exit_gate))]),
                                    html.Div([html.Dt("Frozen source"), html.Dd(gate.source_artifact)]),
                                ]
                            ),
                        ],
                        className="methods-gate-detail",
                    ),
                ],
                className="methods-gate-row",
            )
        )
    return html.Section(
        [
            html.Div([html.H2("Validation gate matrix"), html.P("Gate states are read from frozen reports; the browser does not calculate them.")], className="methods-section-heading"),
            html.Div(
                [
                    html.Div(
                        [html.Span("Validation layer"), html.Span("Status"), html.Span("Checks"), html.Span("Failed"), html.Span("Frozen source")],
                        className="methods-gate-header",
                    ),
                    *rows,
                ],
                className="methods-gate-matrix",
            ),
        ],
        className="methods-card",
    )


def artifact_inventory_panel(frame: pd.DataFrame, locale: object = DEFAULT_LOCALE):
    summary = [
        ("Certified datasets", len(frame)),
        ("Registered fields", int(frame["field_count"].sum())),
        ("Hash-verified datasets", int(frame["hash_verified"].astype(bool).sum())),
        ("Rows across presentation marts", int(frame["row_count"].sum())),
    ]
    columns = [
        {"field": "dataset_name", "headerName": "Dataset", "minWidth": 220},
        {"field": "row_count", "headerName": "Rows", "maxWidth": 100, "filter": False},
        {"field": "field_count", "headerName": "Fields", "maxWidth": 95, "filter": False},
        {"field": "sha256_short", "headerName": "SHA-256", "minWidth": 135},
        {"field": "hash_status", "headerName": "Integrity", "maxWidth": 120},
        {"field": "dashboard_role", "headerName": "Dashboard role", "minWidth": 220},
    ]
    display = frame.copy()
    display["hash_status"] = display["hash_verified"].map({True: "Verified", False: "Not verified"})
    return html.Section(
        [
            html.Div([html.H2("Certified artifact inventory"), html.P("Inventory counts describe release coverage; they are not a scientific quality score.")], className="methods-section-heading"),
            html.Div(
                [
                    html.Div(
                        [html.Strong(format_integer(locale, value)), html.Span(label)]
                    )
                    for label, value in summary
                ],
                className="methods-summary-strip methods-summary-strip--four",
            ),
            html.Details(
                [
                    html.Summary("View certified artifact inventory"),
                    html.Div(
                        data_grid(
                            grid_id=METHODS_ARTIFACT_GRID_ID,
                            frame=display[[item["field"] for item in columns]],
                            column_defs=columns,
                            height=430,
                            page_size=12,
                            class_name="methods-data-grid",
                            locale=locale,
                        ),
                        className="methods-details__body",
                    ),
                ],
                className="methods-details",
            ),
        ],
        className="methods-card",
    )


def experimental_design_snapshot():
    items = [
        ("36", "Canonical cases"),
        ("3", "Narrative LLMs"),
        ("6", "Controlled evidence conditions"),
        ("648", "Planned LLM generations"),
        ("216", "Deterministic Template generations"),
        ("Canonical case", "Primary inference unit"),
    ]
    return html.Section(
        [
            html.Div([html.H2("Experimental design snapshot"), html.P("Template remains a separate deterministic reference, not a fourth LLM.")], className="methods-section-heading"),
            html.Div(
                [html.Div([html.Strong(value), html.Span(label)]) for value, label in items],
                className="methods-design-strip",
            ),
            html.P(
                "One frozen generation occupies each case × LLM × evidence cell. The current study does not estimate stochastic generation stability.",
                className="methods-boundary-note",
            ),
        ],
        className="methods-card",
    )


def research_question_cards(
    records: Iterable[ResearchQuestionRecord],
    *,
    selected: str = "ALL",
    locale: object = DEFAULT_LOCALE,
):
    cards = []
    for item in records:
        if selected != "ALL" and item.rq_id != selected:
            continue
        cards.append(
            html.Article(
                [
                    html.Div(
                        [html.Span(item.rq_id, className="methods-rq-card__id"), html.Span(research_status_label(item.status), className="methods-status methods-status--ready")],
                        className="methods-rq-card__topline",
                    ),
                    html.H3(item.title),
                    html.P(item.question, className="methods-rq-card__question"),
                    html.Dl(
                        [
                            html.Div([html.Dt("Population"), html.Dd(item.population)]),
                            html.Div([html.Dt("Unit of inference"), html.Dd(item.inference_unit)]),
                        ],
                        className="methods-rq-card__facts",
                    ),
                    html.P(
                        [
                            html.Strong("Primary metrics: "),
                            " · ".join(methods_identifier_label(locale, value) for value in item.primary_metrics),
                        ],
                        className="methods-rq-card__primary",
                    ),
                    html.Details(
                        [
                            html.Summary("View method details"),
                            html.Div(
                                [
                                    html.P([html.Strong("Supporting metrics: "), " · ".join(methods_identifier_label(locale, value) for value in item.supporting_metrics) or t(locale, "common.none")]),
                                    html.P([html.Strong("Primary sources: "), " · ".join(item.primary_sources)]),
                                    html.P([html.Strong("Presented on: "), " · ".join(methods_identifier_label(locale, value) for value in item.dashboard_pages)]),
                                    html.Ul([html.Li(value) for value in item.interpretation_restrictions]),
                                ],
                                className="methods-rq-card__details",
                            ),
                        ],
                        className="methods-details methods-details--compact",
                    ),
                ],
                className="methods-rq-card",
            )
        )
    if not cards:
        return html.Div([html.H3("No research question matches this filter"), html.P("Choose another registered RQ.")], className="empty-state")
    return html.Div(cards, className="methods-rq-grid")


def analysis_design_lanes():
    lanes = [
        (
            "Operational analysis",
            "All 648 planned LLM generations",
            "Unusable generations retain operational E2E = 0.",
            "Canonical case with repeated conditions",
        ),
        (
            "Conditional semantic analysis",
            "Usable and common paired generations",
            "Conditional metrics remain missing; observed and excluded pairs are reported.",
            "Paired canonical case",
        ),
        (
            "Complete-case sensitivity",
            "27 cases with all 18 usable LLM conditions",
            "Checks whether structured S4 failures alter conclusions.",
            "Complete canonical case",
        ),
        (
            "Measurement and baseline sensitivity",
            "Candidate–V4 and LLM–Template pairs",
            "Candidate is primary; V4 is sensitivity-only; Template is a separate reference.",
            "Paired canonical case",
        ),
    ]
    return html.Section(
        [
            html.Div([html.H2("Analysis design lanes"), html.P("Operational, conditional and sensitivity analyses use different frozen populations.")], className="methods-section-heading"),
            html.Div(
                [
                    html.Article(
                        [html.H3(title), html.P(population), html.P(policy), html.Small(f"Unit: {unit}")],
                        className="methods-analysis-lane",
                    )
                    for title, population, policy, unit in lanes
                ],
                className="methods-analysis-lanes",
            ),
        ],
        className="methods-card",
    )


def statistical_family_panel(
    frame: pd.DataFrame, locale: object = DEFAULT_LOCALE
):
    rows = [
        html.Tr(
            [
                html.Td(row.family),
                html.Td(format_integer(locale, int(row.frozen_output_count))),
                html.Td(row.unit),
                html.Td(row.role),
            ]
        )
        for row in frame.itertuples(index=False)
    ]
    return html.Section(
        [
            html.Div([html.H2("Frozen statistical families"), html.P("Browser controls select existing tests and never create replacement p-values or correction families.")], className="methods-section-heading"),
            html.Div(
                html.Table(
                    [html.Thead(html.Tr([html.Th("Family"), html.Th("Outputs"), html.Th("Unit"), html.Th("Role")])), html.Tbody(rows)],
                    className="methods-table",
                ),
                className="methods-table-scroll",
            ),
        ],
        className="methods-card",
    )


def denominator_ledger_panel(
    frame: pd.DataFrame, locale: object = DEFAULT_LOCALE
):
    values = frame.set_index("metric_id")["value"].to_dict()
    generation = [
        ("Canonical cases", format_integer(locale, int(values['canonical_cases']))),
        ("Complete 18-condition cases", format_integer(locale, int(values['complete_llm_cases']))),
        ("Cases with structured missingness", format_integer(locale, int(values['incomplete_llm_cases']))),
        ("Planned LLM generations", format_integer(locale, int(values['planned_llm_generations']))),
        ("Usable", format_integer(locale, int(values['usable_llm_generations']))),
        ("Unusable", format_integer(locale, int(values['unusable_llm_generations']))),
    ]
    claims = [
        ("Finalized atomic claims", format_integer(locale, int(values['final_atomic_claims']))),
        ("Applicable claims", format_integer(locale, int(values['applicable_claims']))),
        ("Resolved claims", format_integer(locale, int(values['resolved_claims']))),
    ]
    baseline = [
        ("Canonical cases", "36"),
        ("Evidence conditions", "6"),
        ("Template generations", "216"),
        ("LLM–Template pairs", "648"),
    ]

    def lane(title: str, items: list[tuple[str, str]], note: str):
        return html.Article(
            [
                html.H3(title),
                html.Ol([html.Li([html.Strong(value), html.Span(label)]) for label, value in items]),
                html.P(note),
            ],
            className="methods-denominator-lane",
        )

    return html.Section(
        [
            html.Div([html.H2("Denominator ledger"), html.P("Generation, claim and Template populations are shown as separate lanes to prevent denominator mixing.")], className="methods-section-heading"),
            html.Div(
                [
                    lane("Generation-level population", generation, "Operational E2E retains unusable generations as zero; conditional values remain missing."),
                    lane("Claim-level population", claims, "Verifiability uses all finalized claims; conservative and resolved metrics use their own certified denominators."),
                    lane("Template baseline population", baseline, "Template is compared under the same case and evidence condition and remains outside LLM decision ranking."),
                ],
                className="methods-denominator-grid",
            ),
        ],
        className="methods-card",
    )


def certified_headline_grid(frame: pd.DataFrame, locale: object = DEFAULT_LOCALE):
    display = frame.copy()
    display["metric"] = display["metric_id"].map(lambda value: methods_identifier_label(locale, value))
    display["display_value"] = display.apply(lambda row: _format_certified_value(row, locale), axis=1)
    display["report_section_label"] = display["report_section"].map(
        lambda value: methods_identifier_label(locale, value)
    )
    display["reporting_role_label"] = display["reporting_role"].map(
        lambda value: localized_reporting_role_label(locale, value)
    )
    columns = [
        {"field": "metric", "headerName": "Metric", "minWidth": 230},
        {"field": "display_value", "headerName": "Certified value", "minWidth": 130, "filter": False},
        {"field": "denominator", "headerName": "Denominator", "minWidth": 235},
        {"field": "report_section_label", "headerName": "Section", "minWidth": 150},
        {"field": "reporting_role_label", "headerName": "Reporting role", "minWidth": 170, "cellClass": "methods-reporting-role-cell"},
    ]
    return data_grid(
        grid_id=METHODS_HEADLINE_GRID_ID,
        frame=display[[item["field"] for item in columns]],
        column_defs=columns,
        height=470,
        page_size=12,
        class_name="methods-data-grid",
        locale=locale,
    )


def metric_visibility_cards(frame: pd.DataFrame, locale: object = DEFAULT_LOCALE):
    counts = frame["visibility_tier"].value_counts().to_dict()
    cards = []
    for tier in METHODS_VISIBILITY_TIER_ORDER:
        cards.append(
            html.Article(
                [
                    html.Div(
                        [
                            html.Span(tier.split("_")[0]),
                            html.Strong(
                                t(
                                    locale,
                                    "methods.visibility.metric_count",
                                    count=int(counts.get(tier, 0)),
                                )
                            ),
                        ],
                        className="methods-tier-card__topline",
                    ),
                    html.H3(visibility_tier_label(locale, tier)),
                    html.P(METHODS_VISIBILITY_TIER_DESCRIPTIONS[tier]),
                ],
                className=f"methods-tier-card methods-tier-card--{tier.lower().replace('_', '-')}",
            )
        )
    return html.Div(cards, className="methods-tier-grid")


def metric_dictionary_grid(frame: pd.DataFrame, locale: object = DEFAULT_LOCALE):
    display = frame.copy()
    display["field_label"] = display["field_name"].map(lambda value: methods_identifier_label(locale, value))
    display["nullable_label"] = display["nullable"].map({True: "Nullable", False: "Required"})
    display["tier_label"] = display["visibility_tier"].map(
        lambda value: METHODS_VISIBILITY_TIER_LABELS.get(str(value), "Supporting / identifier")
    )
    display["field_role"] = display.apply(
        lambda row: "Identifier" if bool(row["is_identifier"]) else ("Rate" if bool(row["is_rate"]) else "Supporting field"),
        axis=1,
    )
    columns = [
        {"field": "dataset_name", "headerName": "Dataset", "minWidth": 210},
        {"field": "field_label", "headerName": "Field", "minWidth": 220},
        {"field": "field_name", "headerName": "Technical name", "minWidth": 230},
        {"field": "pandas_dtype", "headerName": "Type", "maxWidth": 115},
        {"field": "nullable_label", "headerName": "Nullability", "maxWidth": 125},
        {"field": "tier_label", "headerName": "Visibility tier", "minWidth": 175},
        {"field": "field_role", "headerName": "Field role", "minWidth": 135},
    ]
    return data_grid(
        grid_id=METHODS_DICTIONARY_GRID_ID,
        frame=display[[item["field"] for item in columns]],
        column_defs=columns,
        height=520,
        page_size=15,
        class_name="methods-data-grid methods-dictionary-grid",
        locale=locale,
    )


def metric_alias_rules():
    rows = [
        ("Resolved faithfulness", "Resolved-error rate", "1 − x"),
        ("Verifiability", "Not-verifiable rate", "1 − x"),
        ("Supported claims per second", "Latency per supported claim", "Reciprocal when positive"),
        ("Usability", "Parse/schema/truncation aliases", "Shared observed failure pattern"),
    ]
    return html.Details(
        [
            html.Summary("View metric alias and deduplication rules"),
            html.Div(
                html.Table(
                    [
                        html.Thead(html.Tr([html.Th("Primary metric"), html.Th("Diagnostic alias"), html.Th("Relationship")])),
                        html.Tbody([html.Tr([html.Td(a), html.Td(b), html.Td(c)]) for a, b, c in rows]),
                    ],
                    className="methods-table",
                ),
                className="methods-details__body methods-table-scroll",
            ),
        ],
        className="methods-details",
    )


def limitation_register(frame: pd.DataFrame):
    if frame.empty:
        return html.Div([html.H3("No limitation records match this filter"), html.P("Choose another category.")], className="empty-state")
    return html.Div(
        [
            html.Details(
                [
                    html.Summary([html.Span(row.category), html.Strong(row.limitation)]),
                    html.Dl(
                        [
                            html.Div([html.Dt("Affected scope"), html.Dd(row.affected_scope)]),
                            html.Div([html.Dt("What it prevents"), html.Dd(row.prevents)]),
                            html.Div([html.Dt("What remains valid"), html.Dd(row.remains_valid)]),
                            html.Div([html.Dt("Required wording"), html.Dd(row.required_wording)]),
                        ],
                        className="methods-limitation-detail",
                    ),
                ],
                className="methods-limitation-row",
            )
            for row in frame.itertuples(index=False)
        ],
        className="methods-limitation-list",
    )


def interpretation_checklist():
    items = [
        "Use canonical case as the inferential unit.",
        "Keep unusable generations in operational denominators.",
        "Preserve missing conditional values rather than replacing them with zero.",
        "Treat S0–S5 as categorical controlled evidence conditions.",
        "Keep Candidate primary and V4 sensitivity-only.",
        "Keep Template outside the LLM ranking.",
        "Report observed paired-case counts.",
        "Treat mechanism findings as associations, not causal effects.",
        "Treat What-if as preference sensitivity, not statistical inference.",
        "Avoid claims about human quality, monetary cost or precise Template latency.",
    ]
    return html.Section(
        [
            html.Div([html.H2("Interpretation checklist"), html.P("Required boundaries for reading and reporting dashboard results.")], className="methods-section-heading"),
            html.Ul([html.Li([html.Span("✓"), html.Span(item)]) for item in items], className="methods-checklist"),
            html.P(
                "Human-perceived quality was not evaluated; utility is not probability or statistical significance.",
                className="methods-boundary-note",
            ),
        ],
        className="methods-card",
    )


def reproduction_workflow(frame: pd.DataFrame):
    steps = []
    for row in frame.sort_values("step_order").itertuples(index=False):
        steps.append(
            html.Li(
                [
                    html.Span(str(int(row.step_order)), className="methods-step__number"),
                    html.Div([html.H3(row.step_label), html.Code(row.command), html.Small(row.status)]),
                ],
                className="methods-step",
            )
        )
    return html.Section(
        [
            html.Div([html.H2("Reproduction workflow"), html.P("Commands are shown exactly as registered for the current repository workflow.")], className="methods-section-heading"),
            html.Ol(steps, className="methods-stepper"),
        ],
        className="methods-card",
    )


def reproduction_status_table():
    rows = [
        ("Certified input verification", "Passed", "Manifest and SHA-256 verification"),
        ("Visualization build", "Passed", "VISUALIZATION_DATA_V2_READY"),
        ("Dashboard unit tests", "Environment-dependent", "Run the registered pytest command"),
        ("Browser E2E", "Requires running server", "Set DASH_E2E_BASE_URL"),
        ("Human calibration", "Not evaluated", "Study limitation"),
        ("Stochastic repeatability", "Not evaluated", "One frozen generation per cell"),
    ]
    return html.Section(
        [
            html.Div([html.H2("Reproduction status"), html.P("Not evaluated is distinct from failed.")], className="methods-section-heading"),
            html.Div(
                html.Table(
                    [
                        html.Thead(html.Tr([html.Th("Layer"), html.Th("Status"), html.Th("Evidence")])),
                        html.Tbody([html.Tr([html.Td(a), html.Td(b), html.Td(c)]) for a, b, c in rows]),
                    ],
                    className="methods-table",
                ),
                className="methods-table-scroll",
            ),
        ],
        className="methods-card",
    )


def methods_global_boundary():
    return html.Section(
        [
            html.Strong("Global interpretation boundary"),
            html.P(
                "Dashboard filters select certified results. They do not create new p-values, redefine correction families, change denominators or promote disabled metrics."
            ),
        ],
        className="methods-global-boundary",
    )
