"""Certified static and archive exports for Page 6 Case Explorer."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from ..data.repository import get_dashboard_repository
from .localization import export_readme
from ..i18n import DEFAULT_LOCALE, localize_plotly_figure, normalize_locale
from ..figures.cases import (
    FIG_CASES_CLAIM_COMPOSITION,
    FIG_CASES_COHORT,
    FIG_CASES_MATRIX,
    FIG_CASES_UTILIZATION,
    FIG_CASES_VALIDATOR_SENSITIVITY,
    build_candidate_v4_case_dumbbell,
    build_case_performance_matrix,
    build_claim_composition,
    build_cohort_landscape,
    build_evidence_utilization_profile,
)
from ..settings import (
    CASE_MATRIX_METRIC_LABELS,
    DASHBOARD_RELEASE_DIR,
    DEFAULT_CASE_EVIDENCE,
    DEFAULT_CASE_MATRIX_METRIC,
    DEFAULT_CASE_MODEL,
    EXPECTED_EVIDENCE_ORDER,
    EXPECTED_MODEL_ORDER,
    ROBUSTNESS_MODEL_LABELS,
)


def _resolve_state(
    case_id: int | None,
    model_id: str,
    evidence_level: str,
    metric_id: str,
) -> tuple[int, str, str, str]:
    repository = get_dashboard_repository()
    catalog = repository.case_catalog()
    valid_cases = set(catalog["case_id"].astype(int))
    resolved_case = int(case_id) if case_id is not None and int(case_id) in valid_cases else int(catalog.iloc[0]["case_id"])
    resolved_model = model_id if model_id in EXPECTED_MODEL_ORDER else DEFAULT_CASE_MODEL
    resolved_evidence = evidence_level if evidence_level in EXPECTED_EVIDENCE_ORDER else DEFAULT_CASE_EVIDENCE
    resolved_metric = metric_id if metric_id in CASE_MATRIX_METRIC_LABELS else DEFAULT_CASE_MATRIX_METRIC
    return resolved_case, resolved_model, resolved_evidence, resolved_metric


def case_figures(
    *,
    case_id: int | None = None,
    model_id: str = DEFAULT_CASE_MODEL,
    evidence_level: str = DEFAULT_CASE_EVIDENCE,
    metric_id: str = DEFAULT_CASE_MATRIX_METRIC,
    locale: object = DEFAULT_LOCALE,
):
    """Build the five canonical Page 6 figures for one selected state."""

    repository = get_dashboard_repository()
    case_id, model_id, evidence_level, metric_id = _resolve_state(
        case_id, model_id, evidence_level, metric_id
    )
    focused = repository.focused_case_data(case_id, model_id, evidence_level)
    figures = {
        FIG_CASES_COHORT: build_cohort_landscape(
            repository.case_catalog(), selected_case_id=case_id
        ),
        FIG_CASES_MATRIX: build_case_performance_matrix(
            repository.case_generation_matrix(case_id, metric_id),
            metric_id=metric_id,
            focused_model_id=model_id,
            focused_evidence_level=evidence_level,
        ),
        FIG_CASES_UTILIZATION: build_evidence_utilization_profile(
            focused.utilization,
            model_id=model_id,
            model_label=ROBUSTNESS_MODEL_LABELS[model_id],
            evidence_level=evidence_level,
        ),
        FIG_CASES_CLAIM_COMPOSITION: build_claim_composition(focused.validator_pair),
        FIG_CASES_VALIDATOR_SENSITIVITY: build_candidate_v4_case_dumbbell(
            focused.validator_pair,
            model_label=ROBUSTNESS_MODEL_LABELS[model_id],
            evidence_level=evidence_level,
        ),
    }
    resolved_locale = normalize_locale(locale)
    return {
        figure_id: localize_plotly_figure(
            figure, resolved_locale, prefixes=("cases.", "common.")
        )
        for figure_id, figure in figures.items()
    }


def build_case_archive(
    *,
    case_id: int,
    model_id: str,
    evidence_level: str,
    metric_id: str,
    locale: object = DEFAULT_LOCALE,
) -> bytes:
    """Return a privacy-preserving ZIP for the current Case Explorer state."""

    repository = get_dashboard_repository()
    case_id, model_id, evidence_level, metric_id = _resolve_state(
        case_id, model_id, evidence_level, metric_id
    )
    focused = repository.focused_case_data(case_id, model_id, evidence_level)
    resolved_locale = normalize_locale(locale)
    figures = case_figures(
        case_id=case_id,
        model_id=model_id,
        evidence_level=evidence_level,
        metric_id=metric_id,
        locale=resolved_locale,
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        figure_manifest: list[dict[str, object]] = []
        for figure_id, figure in figures.items():
            path = f"figures/json/{figure_id}.json"
            archive.writestr(path, figure.to_json(pretty=True))
            figure_manifest.append(
                {"figure_id": figure_id, "path": path, "metadata": dict(figure.layout.meta)}
            )
        archive.writestr(
            "tables/case_summary.csv",
            pd.DataFrame([asdict(focused.case_summary)]).to_csv(index=False),
        )
        archive.writestr(
            "tables/case_generations_24_rows.csv",
            focused.generations.to_csv(index=False),
        )
        archive.writestr(
            "tables/case_evidence_packages_6_rows.csv",
            focused.evidence_packages.to_csv(index=False),
        )
        archive.writestr(
            "tables/focused_generation_utilization.csv",
            focused.utilization.to_frame().T.to_csv(index=False),
        )
        archive.writestr(
            "tables/focused_narrative_structure.csv",
            focused.narrative_structure.to_frame().T.to_csv(index=False),
        )
        archive.writestr(
            "tables/candidate_v4_pair.csv",
            focused.validator_pair.to_frame().T.to_csv(index=False),
        )
        archive.writestr(
            "tables/llm_template_pair.csv",
            focused.template_pair.to_frame().T.to_csv(index=False),
        )
        archive.writestr(
            "README.txt",
            export_readme(
                resolved_locale,
                "cases",
                analytical_release=repository.release.analytical_release_id,
                visualization_release=repository.release.visualization_release_id,
            ),
        )
        archive.writestr(
            "case_export_manifest.json",
            json.dumps(
                {
                    "schema_version": "case_explorer_export_manifest_v1",
                    "analytical_release": repository.release.analytical_release_id,
                    "visualization_release": repository.release.visualization_release_id,
                    "case_id": case_id,
                    "focused_model_id": model_id,
                    "evidence_level": evidence_level,
                    "matrix_metric_id": metric_id,
                    "display_locale": resolved_locale,
                    "candidate_role": "primary",
                    "v4_role": "sensitivity_only",
                    "template_is_fourth_llm": False,
                    "raw_applicant_record_included": False,
                    "direct_personal_identifier_included": False,
                    "figures": figure_manifest,
                },
                indent=2,
            ),
        )
    return buffer.getvalue()


def export_case_figures(
    *,
    output_root: Path = DASHBOARD_RELEASE_DIR,
    formats: tuple[str, ...] = ("json", "svg", "png"),
    case_id: int | None = None,
    model_id: str = DEFAULT_CASE_MODEL,
    evidence_level: str = DEFAULT_CASE_EVIDENCE,
    metric_id: str = DEFAULT_CASE_MATRIX_METRIC,
    locale: object = DEFAULT_LOCALE,
) -> list[Path]:
    """Write report-ready Case Explorer figures for one certified state."""

    created: list[Path] = []
    figures = case_figures(
        case_id=case_id,
        model_id=model_id,
        evidence_level=evidence_level,
        metric_id=metric_id,
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
    parser.add_argument("--case-id", type=int)
    parser.add_argument("--model", default=DEFAULT_CASE_MODEL)
    parser.add_argument("--evidence", default=DEFAULT_CASE_EVIDENCE)
    parser.add_argument("--metric", default=DEFAULT_CASE_MATRIX_METRIC)
    parser.add_argument("--locale", choices=("vi", "en"), default=DEFAULT_LOCALE)
    parser.add_argument("--output-root", type=Path, default=DASHBOARD_RELEASE_DIR)
    args = parser.parse_args()
    formats = tuple(value.strip() for value in args.formats.split(",") if value.strip())
    invalid = sorted(set(formats) - {"json", "svg", "png"})
    if invalid:
        raise SystemExit(f"Unsupported formats: {invalid}")
    created = export_case_figures(
        output_root=args.output_root,
        formats=formats,
        case_id=args.case_id,
        model_id=args.model,
        evidence_level=args.evidence,
        metric_id=args.metric,
        locale=args.locale,
    )
    print(f"Exported {len(created)} Case Explorer figures to {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
