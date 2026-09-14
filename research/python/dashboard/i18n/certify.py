"""Write final dashboard i18n certification artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .certification import certify_dashboard_locales


def write_certification(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = certify_dashboard_locales()
    payload = report.to_dict()

    (output_dir / "i18n_catalog_parity.json").write_text(
        json.dumps(payload["catalog"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "i18n_page_coverage.json").write_text(
        json.dumps(
            {
                "default_locale": payload["default_locale"],
                "pages": payload["pages"],
                "passed": all(item["passed"] for item in payload["pages"]),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "i18n_export_coverage.json").write_text(
        json.dumps(
            {
                "exports": payload["exports"],
                "passed": all(item["passed"] for item in payload["exports"]),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    rows: list[dict[str, str]] = []
    for page in payload["pages"]:
        for kind in ("opposite_locale_leaks", "heuristic_language_leaks"):
            for text in page[kind]:
                rows.append(
                    {
                        "page_id": str(page["page_id"]),
                        "route": str(page["route"]),
                        "locale": str(page["locale"]),
                        "leak_type": kind,
                        "text": str(text),
                    }
                )
    with (output_dir / "i18n_untranslated_strings.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["page_id", "route", "locale", "leak_type", "text"],
        )
        writer.writeheader()
        writer.writerows(rows)

    (output_dir / "i18n_certification_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("release/thesis_dashboard_v1/tests/i18n_certification"),
    )
    args = parser.parse_args()
    payload = write_certification(args.output_dir)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
