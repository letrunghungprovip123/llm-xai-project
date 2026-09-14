"""CLI for ResearchOps Phase 1 governance contracts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .validation import validate_all_contracts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m research.python.researchops.contracts",
        description="Validate machine-readable ResearchOps governance contracts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--json", action="store_true", dest="as_json")
    subparsers.add_parser("hashes")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_all_contracts()

    if args.command == "hashes":
        print(json.dumps(report.hashes, indent=2, sort_keys=True))
        return 0 if report.passed else 1

    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"Checked contracts: {len(report.checked_contracts)}")
        for path, digest in sorted(report.hashes.items()):
            print(f"  {digest}  {path}")
        if report.passed:
            print("Result: GOVERNANCE_CONTRACTS_VALID")
        else:
            print("Result: GOVERNANCE_CONTRACTS_INVALID")
            for issue in report.issues:
                print(f"- [{issue.contract}:{issue.code}] {issue.message}")
    return 0 if report.passed else 1
