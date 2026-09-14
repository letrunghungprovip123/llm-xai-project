#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.python.common_ml.certification import certify_freddie_m13


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify Freddie SFLLD M13 common ML artifacts.")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--canonical-bundle", type=Path, required=True)
    parser.add_argument(
        "--dataset-profile",
        type=Path,
        default=REPO_ROOT / "config/research/datasets/freddie_sflld_2024_v1.json",
    )
    parser.add_argument("--m12-receipt", type=Path, required=True)
    args = parser.parse_args()
    result = certify_freddie_m13(
        workspace=args.workspace,
        dataset_profile_path=args.dataset_profile,
        canonical_bundle_path=args.canonical_bundle,
        m12_receipt_path=args.m12_receipt,
    )
    s = result.summary
    print(f"PASS rows={s['rows']} positives={s['positives']}")
    print(f"PASS model_ready tree={s['tree_features']} linear={s['linear_features']}")
    print(f"PASS best_model={s['best_model']} branch={s['best_branch']}")
    print(f"FREDDIE_M13_RECEIPT={result.receipt_path}")
    print("FREDDIE_SFLLD_M13_COMMON_ML=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
