"""Report-ready static exports for Page 2."""

from __future__ import annotations

import argparse
from pathlib import Path

import plotly.graph_objects as go

from ..data.repository import DashboardRepository, get_dashboard_repository
from ..figures.effectiveness import (
    FIG_EFFECTIVENESS_CONDITIONAL_HEATMAP,
    FIG_EFFECTIVENESS_LOSS_DECOMPOSITION,
    FIG_EFFECTIVENESS_OPERATIONAL_CONDITIONAL_GAP,
    FIG_EFFECTIVENESS_PRIMARY_EFFECT_SIZES,
    FIG_EFFECTIVENESS_RELIABILITY_MAP,
    build_conditional_quality_heatmap,
    build_effect_size_chart,
    build_operational_conditional_gap,
    build_operational_loss_decomposition,
    build_reliability_map,
)
from ..settings import (
    CONDITIONAL_METRIC_LABELS,
    DASHBOARD_RELEASE_DIR,
    DEFAULT_CONDITIONAL_METRIC,
)


def effectiveness_figures(
    repository: DashboardRepository | None = None,
) -> dict[str, go.Figure]:
    repo = repository or get_dashboard_repository()
    data = repo.effectiveness_data()
    summary = repo.conditional_option_summary(DEFAULT_CONDITIONAL_METRIC)
    label = CONDITIONAL_METRIC_LABELS[DEFAULT_CONDITIONAL_METRIC]
    return {
        FIG_EFFECTIVENESS_RELIABILITY_MAP: build_reliability_map(
            data.option_performance
        ),
        FIG_EFFECTIVENESS_LOSS_DECOMPOSITION: (
            build_operational_loss_decomposition(data.option_performance)
        ),
        FIG_EFFECTIVENESS_CONDITIONAL_HEATMAP: (
            build_conditional_quality_heatmap(
                summary,
                metric_id=DEFAULT_CONDITIONAL_METRIC,
                metric_label=label,
            )
        ),
        FIG_EFFECTIVENESS_OPERATIONAL_CONDITIONAL_GAP: (
            build_operational_conditional_gap(
                summary,
                metric_id=DEFAULT_CONDITIONAL_METRIC,
                metric_label=label,
            )
        ),
        FIG_EFFECTIVENESS_PRIMARY_EFFECT_SIZES: build_effect_size_chart(
            data.omnibus_tests
        ),
    }


def export_effectiveness_figures(
    *,
    output_root: Path = DASHBOARD_RELEASE_DIR,
    formats: tuple[str, ...] = ("json", "svg", "png"),
    repository: DashboardRepository | None = None,
) -> list[Path]:
    figures = effectiveness_figures(repository)
    created: list[Path] = []
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
                        "Static image export failed. Verify Kaleido and "
                        "Chrome/Chromium with `plotly_get_chrome -y`."
                    ) from exc
            created.append(target)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formats", default="json,svg,png")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DASHBOARD_RELEASE_DIR,
    )
    args = parser.parse_args()
    formats = tuple(item.strip() for item in args.formats.split(",") if item.strip())
    invalid = sorted(set(formats) - {"json", "svg", "png"})
    if invalid:
        raise SystemExit(f"Unsupported formats: {invalid}")
    created = export_effectiveness_figures(
        output_root=args.output_root,
        formats=formats,
    )
    print(f"Exported {len(created)} files to {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
