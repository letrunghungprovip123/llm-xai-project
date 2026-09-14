#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.python.datasets.freddie_sflld.preparation import FeaturePolicy, TARGET_SOURCE_COLUMN
from research.python.datasets.freddie_sflld.schema import PERFORMANCE_COLUMNS
from research.python.datasets.intake import evaluate_replication_profile
from research.python.datasets.profile import load_canonical_bundle, load_dataset_profile, sha256_json
from research.python.datasets.receipts import load_receipt, sha256_path


def check(name: str, actual, expected) -> bool:
    ok = actual == expected
    print(f"{'PASS' if ok else 'FAIL'} {name}: actual={actual!r} expected={expected!r}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Independently verify Freddie M12 canonical preparation artifacts.")
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument(
        "--dataset-profile", type=Path,
        default=REPO_ROOT / "config/research/datasets/freddie_sflld_2024_v1.json",
    )
    parser.add_argument(
        "--feature-policy", type=Path,
        default=REPO_ROOT / "config/research/datasets/freddie_sflld_2024_feature_policy_v1.json",
    )
    args = parser.parse_args()
    root = args.artifact_root.expanduser().resolve()
    profile = load_dataset_profile(args.dataset_profile)
    policy = FeaturePolicy.load(args.feature_policy)
    bundle_path = root / "data/manifests/canonical_dataset_bundle_freddie_sflld_2024_v1.json"
    manifest_path = root / "data/manifests/freddie_sflld_2024_preparation_manifest_v1.json"
    receipt_path = root / "data/manifests/freddie_sflld_2024_m12_preparation_receipt_v1.json"
    bundle = load_canonical_bundle(bundle_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt = load_receipt(receipt_path)
    target_manifest = json.loads((args.target_dir / "freddie_target_12m_manifest_v1.json").read_text(encoding="utf-8"))

    def artifact(name: str) -> Path:
        ref = bundle.artifacts[name]
        path = root / ref.path
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    X_path = artifact("feature_matrix")
    y_path = artifact("target")
    registry_path = artifact("feature_registry_csv")
    feature_yaml_path = artifact("feature_registry_yaml")
    concept_path = artifact("concept_registry_yaml")
    X = pd.read_parquet(X_path)
    y = pd.read_parquet(y_path)
    registry = pd.read_csv(registry_path)
    feature_yaml = yaml.safe_load(feature_yaml_path.read_text(encoding="utf-8"))
    concept_yaml = yaml.safe_load(concept_path.read_text(encoding="utf-8"))

    model_columns = [column for column in X.columns if column != profile.entity.source_id_column]
    performance_overlap = sorted((set(model_columns) & set(PERFORMANCE_COLUMNS)))
    registry_names = registry["feature_name"].astype(str).tolist()
    concepts = set((concept_yaml.get("concepts") or {}).keys())
    target_expected_rows = int(target_manifest["totals"]["eligible"])
    target_expected_positive = int(target_manifest["totals"]["positive"])
    report = evaluate_replication_profile(profile, bundle)

    checks = [
        check("dataset_id", bundle.dataset_id, profile.dataset_id),
        check("dataset_version", bundle.dataset_version, profile.dataset_version),
        check("dataset_profile_sha256", bundle.dataset_profile_sha256, sha256_json(profile.to_dict())),
        check("rows.feature_matrix", len(X), target_expected_rows),
        check("rows.target", len(y), target_expected_rows),
        check("positive", int(y[TARGET_SOURCE_COLUMN].sum()), target_expected_positive),
        check("target_values", sorted(y[TARGET_SOURCE_COLUMN].unique().tolist()), [0, 1]),
        check("feature_count", len(model_columns), len(policy.primary_features)),
        check("feature_columns", model_columns, policy.feature_names),
        check("registry_feature_names", registry_names, policy.feature_names),
        check("feature_yaml_count", len(feature_yaml.get("features", {})), len(policy.primary_features)),
        check("unknown_concepts", sorted(set(registry["concept"].astype(str)) - concepts), []),
        check("performance_fields_in_X", performance_overlap, []),
        check("X_id_unique", int(X[profile.entity.source_id_column].duplicated().sum()), 0),
        check("y_id_unique", int(y[profile.entity.source_id_column].duplicated().sum()), 0),
        check(
            "X_y_identity_sets",
            set(X[profile.entity.source_id_column].astype(str)) == set(y[profile.entity.source_id_column].astype(str)),
            True,
        ),
        check("manifest_performance_leakage", manifest["performance_features_in_X"], []),
        check("dataset_fingerprint_recomputed", bundle.dataset_fingerprint, sha256_json(manifest["fingerprint_inputs"])),
        check("receipt_status", receipt.status, "PASS"),
        check("receipt_dataset", receipt.dataset_id, profile.dataset_id),
        check("profile_gate_has_failures", len(report.failures), 0),
    ]
    for name, ref in bundle.artifacts.items():
        checks.append(check(f"artifact_hash.{name}", sha256_path(root / ref.path), ref.sha256))
    for name, digest in receipt.output_fingerprints.items():
        path_candidates = [
            root / "data/processed" / name,
            root / "ml/registry" / name,
            root / "data/manifests" / name,
        ]
        path = next((candidate for candidate in path_candidates if candidate.is_file()), None)
        checks.append(check(f"receipt_output_exists.{name}", path is not None, True))
        if path is not None:
            checks.append(check(f"receipt_hash.{name}", sha256_path(path), digest))

    if all(checks):
        print(f"FREDDIE_REPLICATION_PROFILE_STATUS={report.status}")
        if report.warnings:
            for warning in report.warnings:
                print(f"WARN {warning.check_id}: {warning.detail}")
        print("FREDDIE_SFLLD_M12_PREPARATION=PASS")
        return 0
    print("FREDDIE_SFLLD_M12_PREPARATION=FAIL")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
