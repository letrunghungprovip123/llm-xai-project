"""Report-ready static and archive exports for Page 5."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from ..data.repository import get_dashboard_repository
from .localization import export_readme
from ..figures.robustness import (
    FIG_ROBUSTNESS_MEASUREMENT_DELTA,
    FIG_ROBUSTNESS_MEASUREMENT_SHIFT,
    FIG_ROBUSTNESS_TEMPLATE_COVERAGE,
    FIG_ROBUSTNESS_TEMPLATE_DELTA,
    FIG_ROBUSTNESS_TEMPLATE_PROGRESSION,
    FIG_ROBUSTNESS_TEMPLATE_UPLIFT,
    build_candidate_v4_delta_distribution,
    build_candidate_v4_dumbbell,
    build_template_coverage_scatter,
    build_template_delta_distribution,
    build_template_evidence_progression,
    build_template_uplift_matrix,
)
from ..i18n import DEFAULT_LOCALE, localize_plotly_figure, normalize_locale
from ..settings import (
    DASHBOARD_RELEASE_DIR,
    DEFAULT_ROBUSTNESS_METRIC,
    DEFAULT_TEMPLATE_METRIC,
    DEFAULT_TEMPLATE_SCOPE,
    EXPECTED_MODEL_ORDER,
    ROBUSTNESS_MODEL_LABELS,
    TEMPLATE_SCOPE_LABELS,
)


def _template_tests_for_figures(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach presentation labels without importing Dash page modules."""

    display = frame.copy()
    display["model_label"] = display["model_id"].map(ROBUSTNESS_MODEL_LABELS)
    display["model_order"] = display["model_id"].map(
        {model_id: index for index, model_id in enumerate(EXPECTED_MODEL_ORDER, start=1)}
    )
    return display


def robustness_figures(
    *,
    measurement_metric: str = DEFAULT_ROBUSTNESS_METRIC,
    template_metric: str = DEFAULT_TEMPLATE_METRIC,
    template_scope: str = DEFAULT_TEMPLATE_SCOPE,
    locale: object = DEFAULT_LOCALE,
):
    """Build the six canonical Page 5 figures from certified presentation data."""

    repository = get_dashboard_repository()
    measurement_summary = repository.measurement_shift_summary(measurement_metric)
    measurement_row = measurement_summary.iloc[
        measurement_summary["mean_delta_v4_minus_candidate"].abs().argmax()
    ]
    measurement_cases = repository.measurement_case_deltas(
        measurement_metric,
        str(measurement_row["model_id"]),
        str(measurement_row["evidence_level"]),
    )

    template_summary = repository.template_uplift_summary(template_metric, template_scope)
    template_row = template_summary.iloc[
        template_summary["mean_delta_llm_minus_template"].abs().argmax()
    ]
    template_cases = repository.template_case_deltas(
        template_metric,
        str(template_row["model_id"]),
        template_scope,
    )
    tests = _template_tests_for_figures(repository.llm_vs_template_tests())

    figures = {
        FIG_ROBUSTNESS_MEASUREMENT_SHIFT: build_candidate_v4_dumbbell(
            measurement_summary,
            metric_id=measurement_metric,
        ),
        FIG_ROBUSTNESS_MEASUREMENT_DELTA: build_candidate_v4_delta_distribution(
            measurement_cases,
            metric_id=measurement_metric,
            focus_label=(
                f"{measurement_row['model_label']} · {measurement_row['evidence_level']}"
            ),
        ),
        FIG_ROBUSTNESS_TEMPLATE_PROGRESSION: build_template_evidence_progression(
            repository.llm_vs_template_summary(),
            repository.baseline_option_performance(),
            metric_id=template_metric,
        ),
        FIG_ROBUSTNESS_TEMPLATE_UPLIFT: build_template_uplift_matrix(
            tests,
            evidence_scope=template_scope,
        ),
        FIG_ROBUSTNESS_TEMPLATE_DELTA: build_template_delta_distribution(
            template_cases,
            metric_id=template_metric,
            focus_label=(
                f"{ROBUSTNESS_MODEL_LABELS[str(template_row['model_id'])]} · "
                f"{TEMPLATE_SCOPE_LABELS[template_scope]}"
            ),
        ),
        FIG_ROBUSTNESS_TEMPLATE_COVERAGE: build_template_coverage_scatter(
            repository.llm_vs_template_summary(),
            repository.baseline_option_performance(),
        ),
    }
    return {
        figure_id: localize_plotly_figure(figure, locale, prefixes=("robustness.",))
        for figure_id, figure in figures.items()
    }


def build_robustness_archive(locale: object = DEFAULT_LOCALE) -> bytes:
    """Return a reproducible ZIP with figures, frozen tests, and release metadata."""

    repository = get_dashboard_repository()
    resolved_locale = normalize_locale(locale)
    figures = robustness_figures(locale=resolved_locale)
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        manifest: list[dict[str, object]] = []
        for figure_id, figure in figures.items():
            path = f"figures/json/{figure_id}.json"
            archive.writestr(path, figure.to_json(pretty=True))
            manifest.append(
                {
                    "figure_id": figure_id,
                    "path": path,
                    "metadata": dict(figure.layout.meta),
                }
            )
        archive.writestr(
            "tables/validator_sensitivity_tests.csv",
            repository.validator_sensitivity_tests().to_csv(index=False),
        )
        archive.writestr(
            "tables/llm_vs_template_tests.csv",
            repository.llm_vs_template_tests().to_csv(index=False),
        )
        archive.writestr(
            "README.txt",
            export_readme(
                resolved_locale,
                "robustness",
                analytical_release=repository.release.analytical_release_id,
                visualization_release=repository.release.visualization_release_id,
            ),
        )
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "schema_version": "robustness_export_manifest_v1",
                    "analytical_release": repository.release.analytical_release_id,
                    "visualization_release": repository.release.visualization_release_id,
                    "candidate_role": "primary",
                    "v4_role": "sensitivity_only",
                    "template_is_fourth_llm": False,
                    "template_eligible_for_decision_ranking": False,
                    "display_locale": resolved_locale,
                    "figures": manifest,
                },
                indent=2,
            ),
        )
    return buffer.getvalue()


def export_robustness_figures(
    *,
    output_root: Path = DASHBOARD_RELEASE_DIR,
    formats: tuple[str, ...] = ("json", "svg", "png"),
    measurement_metric: str = DEFAULT_ROBUSTNESS_METRIC,
    template_metric: str = DEFAULT_TEMPLATE_METRIC,
    template_scope: str = DEFAULT_TEMPLATE_SCOPE,
    locale: object = DEFAULT_LOCALE,
) -> list[Path]:
    """Write report-ready figure files for a certified Page 5 state."""

    created: list[Path] = []
    figures = robustness_figures(
        measurement_metric=measurement_metric,
        template_metric=template_metric,
        template_scope=template_scope,
        locale=locale,
    )
    for file_format in formats:
        target_dir = output_root / "figures" / file_format
        target_dir.mkdir(parents=True, exist_ok=True)
        for figure_id, figure in figures.items():
            target = target_dir / f"{figure_id}.{file_format}"
            if file_format == "json":
                target.write_text(figure.to_json(pretty=True), encoding="utf-8")
            else:
                try:
                    figure.write_image(target, width=1600, height=900, scale=1)
                except Exception as exc:
                    raise RuntimeError(
                        "Static image export failed. Verify Kaleido and Chrome/Chromium "
                        "with `plotly_get_chrome -y`."
                    ) from exc
            created.append(target)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formats", default="json,svg,png")
    parser.add_argument("--measurement-metric", default=DEFAULT_ROBUSTNESS_METRIC)
    parser.add_argument("--template-metric", default=DEFAULT_TEMPLATE_METRIC)
    parser.add_argument("--template-scope", default=DEFAULT_TEMPLATE_SCOPE)
    parser.add_argument("--output-root", type=Path, default=DASHBOARD_RELEASE_DIR)
    parser.add_argument("--locale", choices=("vi", "en"), default=DEFAULT_LOCALE)
    args = parser.parse_args()
    formats = tuple(item.strip() for item in args.formats.split(",") if item.strip())
    invalid = sorted(set(formats) - {"json", "svg", "png"})
    if invalid:
        raise SystemExit(f"Unsupported formats: {invalid}")
    created = export_robustness_figures(
        output_root=args.output_root,
        formats=formats,
        measurement_metric=args.measurement_metric,
        template_metric=args.template_metric,
        template_scope=args.template_scope,
        locale=args.locale,
    )
    print(f"Exported {len(created)} files to {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
