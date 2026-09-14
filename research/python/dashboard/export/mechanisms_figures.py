"""Report-ready static exports for Page 3."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..callbacks.mechanisms import mechanisms_figures
from ..settings import DASHBOARD_RELEASE_DIR


def export_mechanisms_figures(*, output_root: Path = DASHBOARD_RELEASE_DIR, formats: tuple[str, ...] = ("json", "svg", "png")) -> list[Path]:
    created: list[Path] = []
    for file_format in formats:
        target_dir = output_root / "figures" / file_format
        target_dir.mkdir(parents=True, exist_ok=True)
        for figure_id, figure in mechanisms_figures().items():
            target = target_dir / f"{figure_id}.{file_format}"
            if file_format == "json":
                target.write_text(figure.to_json(pretty=True), encoding="utf-8")
            else:
                try:
                    figure.write_image(target, width=1600, height=900, scale=1)
                except Exception as exc:
                    raise RuntimeError("Static image export failed. Verify Kaleido and Chrome/Chromium with `plotly_get_chrome -y`.") from exc
            created.append(target)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formats", default="json,svg,png")
    parser.add_argument("--output-root", type=Path, default=DASHBOARD_RELEASE_DIR)
    args = parser.parse_args()
    formats = tuple(item.strip() for item in args.formats.split(",") if item.strip())
    invalid = sorted(set(formats) - {"json", "svg", "png"})
    if invalid:
        raise SystemExit(f"Unsupported formats: {invalid}")
    created = export_mechanisms_figures(output_root=args.output_root, formats=formats)
    print(f"Exported {len(created)} files to {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
