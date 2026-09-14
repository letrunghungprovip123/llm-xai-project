#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.python.datasets.freddie_sflld.raw_intake import QUARTERS
from research.python.datasets.freddie_sflld.target_builder import FreddieTargetBuilder


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the frozen Freddie 12-month serious-delinquency target.")
    parser.add_argument("--raw-zip", type=Path, required=True)
    parser.add_argument("--m11-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--target-protocol",
        type=Path,
        default=REPO_ROOT / "config/research/datasets/freddie_sflld_2024_target_protocol_v1.json",
    )
    parser.add_argument("--quarter", choices=QUARTERS, help=argparse.SUPPRESS)
    parser.add_argument("--finalize-only", action="store_true", help=argparse.SUPPRESS)
    return parser


def _worker_command(args: argparse.Namespace, quarter: str) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "--raw-zip", str(args.raw_zip),
        "--m11-dir", str(args.m11_dir),
        "--output-dir", str(args.output_dir),
        "--target-protocol", str(args.target_protocol),
        "--quarter", quarter,
    ]


def main() -> int:
    args = _parser().parse_args()
    builder = FreddieTargetBuilder(
        raw_zip=args.raw_zip,
        protocol_path=args.target_protocol,
        m11_dir=args.m11_dir,
    )
    if args.quarter:
        result = builder.run_quarter(args.output_dir, args.quarter)
        stats = result["stats"]
        print(
            f"FREDDIE_TARGET_PARTITION=PASS quarter={args.quarter} "
            f"loans={stats['loans']} eligible={stats['eligible']} positive={stats['positive']} "
            f"censored={stats['censored']}"
        )
        return 0
    if not args.finalize_only:
        # One fresh interpreter per quarter.  The production scanner itself is
        # streaming and bounded-memory; process isolation additionally makes the
        # multi-quarter build resumable and prevents allocator state from one
        # multi-million-row compressed stream carrying into the next quarter.
        for quarter in QUARTERS:
            subprocess.run(_worker_command(args, quarter), check=True)
    result = builder.finalize(args.output_dir)
    totals = result.manifest["totals"]
    print(
        "FREDDIE_TARGET_12M=PASS "
        f"loans={totals['loans']} eligible={totals['eligible']} positive={totals['positive']} "
        f"negative={totals['negative']} censored={totals['censored']} "
        f"positive_rate={totals['positive_rate_eligible']:.12f}"
    )
    print(f"FREDDIE_TARGET_MANIFEST={result.manifest_path}")
    print(f"FREDDIE_M12A_RECEIPT={result.receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
