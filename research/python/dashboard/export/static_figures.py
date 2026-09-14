"""Certified Page-1 export helpers and command-line static export."""

from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import plotly.graph_objects as go

from ..data.repository import DashboardRepository, get_dashboard_repository
from ..i18n import DEFAULT_LOCALE, evidence_label, localize_plotly_figure, normalize_locale, t
from ..figures.overview import (
    FIG_OVERVIEW_E2E_HEATMAP,
    FIG_OVERVIEW_EVIDENCE_PROFILE,
    build_e2e_option_heatmap,
    build_evidence_profile,
)
from ..settings import DASHBOARD_RELEASE_DIR


def overview_figures(
    repository: DashboardRepository | None = None,
    *,
    locale: object = DEFAULT_LOCALE,
) -> dict[str, go.Figure]:
    repo = repository or get_dashboard_repository()
    resolved = normalize_locale(locale)
    options = repo.option_performance().copy(deep=True)
    options["evidence_label"] = options["evidence_level"].map(
        lambda value: evidence_label(resolved, value)
    )
    prefixes = ("overview.figure.",)
    return {
        FIG_OVERVIEW_E2E_HEATMAP: localize_plotly_figure(
            build_e2e_option_heatmap(options), resolved, prefixes=prefixes
        ),
        FIG_OVERVIEW_EVIDENCE_PROFILE: localize_plotly_figure(
            build_evidence_profile(options), resolved, prefixes=prefixes
        ),
    }


def build_overview_export_archive(
    repository: DashboardRepository | None = None,
    *,
    locale: object = DEFAULT_LOCALE,
) -> bytes:
    """Return a small reproducible ZIP without requiring Chrome/Kaleido."""

    repo = repository or get_dashboard_repository()
    resolved = normalize_locale(locale)
    figures = overview_figures(repo, locale=resolved)
    buffer = BytesIO()
    manifest: list[dict[str, object]] = []

    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for figure_id, figure in figures.items():
            payload = figure.to_json(pretty=True).encode("utf-8")
            filename = f"figures/json/{figure_id}.json"
            archive.writestr(filename, payload)
            manifest.append(
                {
                    "figure_id": figure_id,
                    "path": filename,
                    "sha256": sha256(payload).hexdigest(),
                    "metadata": dict(figure.layout.meta),
                }
            )

        readme = "\n".join(
            [
                t(resolved, "overview.export.bundle_title"),
                t(
                    resolved,
                    "overview.export.analytical_release",
                    release=repo.release.analytical_release_id,
                ),
                t(
                    resolved,
                    "overview.export.visualization_release",
                    release=repo.release.visualization_release_id,
                ),
                t(resolved, "overview.export.json_note"),
                t(resolved, "overview.export.static_note"),
            ]
        ) + "\n"
        archive.writestr("README.txt", readme)
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "schema_version": "overview_export_manifest_v1",
                    "analytical_release": repo.release.analytical_release_id,
                    "visualization_release": repo.release.visualization_release_id,
                    "display_locale": resolved,
                    "figures": manifest,
                },
                indent=2,
                ensure_ascii=False,
            ),
        )

    return buffer.getvalue()


def export_overview_figures(
    *,
    output_root: Path = DASHBOARD_RELEASE_DIR,
    formats: tuple[str, ...] = ("json", "svg", "png"),
    repository: DashboardRepository | None = None,
    locale: object = DEFAULT_LOCALE,
) -> list[Path]:
    """Write report-ready figures and return created files."""

    figures = overview_figures(repository, locale=locale)
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
                except Exception as exc:  # Kaleido/Chrome environment boundary.
                    raise RuntimeError(
                        "Static image export failed. Verify Kaleido and Chrome/Chromium "
                        "with `plotly_get_chrome -y`."
                    ) from exc
            created.append(target)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--formats",
        default="json,svg,png",
        help="Comma-separated subset of json,svg,png",
    )
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
    created = export_overview_figures(
        output_root=args.output_root,
        formats=formats,
    )
    print(f"Exported {len(created)} files to {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
