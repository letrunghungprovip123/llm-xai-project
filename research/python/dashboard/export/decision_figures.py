"""Report-ready static exports for Page 4 — Decision Studio."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..callbacks.decision import decision_figures
from ..i18n import DEFAULT_LOCALE
from ..settings import DASHBOARD_RELEASE_DIR, DEFAULT_DECISION_SCENARIO


def export_decision_figures(
    *,
    output_root: Path = DASHBOARD_RELEASE_DIR,
    formats: tuple[str, ...] = ("json", "svg", "png"),
    scenario_id: str = DEFAULT_DECISION_SCENARIO,
    locale: object = DEFAULT_LOCALE,
) -> list[Path]:
    created: list[Path] = []
    for file_format in formats:
        target_dir = output_root / "figures" / file_format
        target_dir.mkdir(parents=True, exist_ok=True)
        for figure_id, figure in decision_figures(scenario_id, locale=locale).items():
            target = target_dir / f"{figure_id}.{file_format}"
            if file_format == "json":
                target.write_text(figure.to_json(pretty=True), encoding="utf-8")
            else:
                try:
                    figure.write_image(target, width=1600, height=900, scale=1)
                except Exception as exc:
                    raise RuntimeError(
                        "Static image export failed. Verify Kaleido and Chrome/Chromium with `plotly_get_chrome -y`."
                    ) from exc
            created.append(target)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formats", default="json,svg,png")
    parser.add_argument("--scenario", default=DEFAULT_DECISION_SCENARIO)
    parser.add_argument("--output-root", type=Path, default=DASHBOARD_RELEASE_DIR)
    parser.add_argument("--locale", choices=("vi", "en"), default=DEFAULT_LOCALE)
    args = parser.parse_args()
    formats = tuple(item.strip() for item in args.formats.split(",") if item.strip())
    invalid = sorted(set(formats) - {"json", "svg", "png"})
    if invalid:
        raise SystemExit(f"Unsupported formats: {invalid}")
    created = export_decision_figures(
        output_root=args.output_root,
        formats=formats,
        scenario_id=args.scenario,
        locale=args.locale,
    )
    print(f"Exported {len(created)} files to {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
