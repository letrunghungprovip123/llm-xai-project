"""Certified release badges and compact gate strip."""

from __future__ import annotations

from dash import html

from ..data.contracts import GateStatus, ReleaseMetadata
from ..i18n import DEFAULT_LOCALE, normalize_locale, t


def release_badge(
    release: ReleaseMetadata,
    locale: object = DEFAULT_LOCALE,
):
    """Render the compact analytical release identity in the app header."""

    resolved_locale = normalize_locale(locale)
    return html.Span(
        [
            html.Span(className="release-badge__dot", **{"aria-hidden": "true"}),
            html.Span(
                t(
                    resolved_locale,
                    "app.release_certified",
                    release_id=release.visualization_release_id,
                )
            ),
        ],
        className="release-badge",
        title=t(
            resolved_locale,
            "app.release_tooltip",
            analytical_release=release.analytical_release_id,
            commit=release.parent_git_commit,
            dataset_count=release.dataset_count,
        ),
    )


def gate_item(gate: GateStatus, locale: object = DEFAULT_LOCALE):
    resolved_locale = normalize_locale(locale)
    state = "ready" if gate.passed else "blocked"
    label_key = f"app.release_gate_{state}"
    return html.Span(
        [
            html.Span(className=f"gate-dot gate-dot--{state}"),
            html.Span(gate.gate_id),
        ],
        className=f"gate-item gate-item--{state}",
        title=t(resolved_locale, label_key, gate=gate.gate_id),
    )


def release_strip(
    release: ReleaseMetadata,
    locale: object = DEFAULT_LOCALE,
):
    """Render compact certified release counts without recalculating gates."""

    resolved_locale = normalize_locale(locale)
    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        t(
                            resolved_locale,
                            "app.release_dataset_count",
                            count=release.dataset_count,
                        )
                    ),
                    html.Span("·"),
                    html.Span(
                        t(
                            resolved_locale,
                            "app.release_check_count",
                            count=release.validation_check_count,
                        )
                    ),
                    html.Span("·"),
                    html.Span(
                        t(
                            resolved_locale,
                            "app.release_rq_count",
                            count=release.research_question_count,
                        )
                    ),
                ],
                className="release-strip__summary",
            ),
        ],
        className="release-strip",
        role="status",
        **{"aria-label": t(resolved_locale, "app.release_aria")},
    )


__all__ = ["gate_item", "release_badge", "release_strip"]
