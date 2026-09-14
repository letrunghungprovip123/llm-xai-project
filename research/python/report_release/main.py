"""Generate the final report-writing release bundle."""

from __future__ import annotations

import argparse
import json

from .build import (
    build_manifest,
    build_report_numbers,
    build_source_index,
    load_gates,
    validate_readiness,
)
from .config import (
    MANIFEST_PATH,
    OUTPUT_DIR,
    READINESS_PATH,
    REPORT_NUMBERS_PATH,
    SOURCE_INDEX_PATH,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-dirty-preview",
        action="store_true",
        help="Build a preview but keep the final clean-Git gate disabled.",
    )
    arguments = parser.parse_args()

    gates = load_gates()
    numbers = build_report_numbers()
    source_index = build_source_index()
    manifest = build_manifest(gates)
    readiness = validate_readiness(
        gates,
        manifest,
        numbers,
        require_clean_git=not arguments.allow_dirty_preview,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_NUMBERS_PATH.write_text(
        json.dumps(numbers, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    source_index.to_csv(SOURCE_INDEX_PATH, index=False)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    READINESS_PATH.write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    print("Report release")
    print(f"- Certified files: {len(manifest['certified_report_files'])}")
    print(f"- Checks: {readiness['check_count']}")
    print(f"- Failed: {readiness['failed_check_count']}")
    print(f"- Exit gate: {readiness['exit_gate']}")
    return 0 if readiness["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
