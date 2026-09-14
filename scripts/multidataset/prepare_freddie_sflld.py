#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.python.datasets.freddie_sflld.preparation import FreddieMacSFLLDPreparationAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Freddie SFLLD 2024 into CanonicalDatasetBundleV1.")
    parser.add_argument("--raw-zip", type=Path, required=True)
    parser.add_argument("--m11-dir", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--dataset-profile", type=Path,
        default=REPO_ROOT / "config/research/datasets/freddie_sflld_2024_v1.json",
    )
    parser.add_argument(
        "--feature-policy", type=Path,
        default=REPO_ROOT / "config/research/datasets/freddie_sflld_2024_feature_policy_v1.json",
    )
    parser.add_argument(
        "--concept-registry", type=Path,
        default=REPO_ROOT / "config/research/datasets/freddie_sflld_2024_concept_registry_v1.yaml",
    )
    parser.add_argument("--bundle-output", type=Path)
    args = parser.parse_args()

    adapter = FreddieMacSFLLDPreparationAdapter(
        raw_zip=args.raw_zip,
        m11_dir=args.m11_dir,
        target_dir=args.target_dir,
        profile_path=args.dataset_profile,
        feature_policy_path=args.feature_policy,
        concept_registry_path=args.concept_registry,
    )
    preflight = adapter.validate_source()
    if preflight.get("status") != "passed":
        raise RuntimeError(f"Freddie preparation preflight blocked: {preflight}")
    result = adapter.build_canonical_bundle(args.output_root, args.bundle_output)
    print(
        "FREDDIE_PREPARATION=PASS "
        f"rows={result.manifest['rows']} positive={result.manifest['positive']} "
        f"features={result.manifest['primary_feature_count']}"
    )
    print(f"FREDDIE_DATASET_FINGERPRINT={result.bundle.dataset_fingerprint}")
    print(f"FREDDIE_CANONICAL_BUNDLE={result.bundle_path}")
    print(f"FREDDIE_M12_RECEIPT={result.receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
