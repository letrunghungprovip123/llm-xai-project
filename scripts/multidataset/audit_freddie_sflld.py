#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.python.datasets.freddie_sflld.raw_intake import FreddieRawIntakeAuditor


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a Freddie SFLLD vintage ZIP without mutating it.")
    parser.add_argument("--raw-zip", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = FreddieRawIntakeAuditor(args.raw_zip).run(args.output_dir)
    totals = result.audit["totals"]
    print(
        "FREDDIE_RAW_INTAKE=PASS "
        f"origination_rows={totals['origination_rows']} "
        f"performance_rows={totals['performance_rows']} "
        f"performance_cutoff={totals['max_reporting_period']}"
    )
    print(f"FREDDIE_RAW_MANIFEST={result.manifest_path}")
    print(f"FREDDIE_M11_RECEIPT={result.receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
