#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.python.datasets.intake import FAIL, evaluate_replication_profile
from research.python.datasets.profile import load_canonical_bundle, load_dataset_profile


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preflight a dataset profile for exact multi-dataset LLM-XAI replication."
    )
    parser.add_argument("--dataset-profile", required=True, type=Path)
    parser.add_argument("--canonical-bundle", type=Path)
    parser.add_argument(
        "--allow-legacy-target-semantics",
        action="store_true",
        help="Compatibility-only option for the historical Home Credit profile.",
    )
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    profile = load_dataset_profile(args.dataset_profile)
    bundle = load_canonical_bundle(args.canonical_bundle) if args.canonical_bundle else None
    report = evaluate_replication_profile(
        profile,
        bundle,
        require_explicit_target_semantics=not args.allow_legacy_target_semantics,
    )

    for check in report.checks:
        print(f"{check.status} {check.check_id}: {check.detail}")
    print(f"DATASET_REPLICATION_PROFILE={report.status}")

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if report.status == FAIL:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
