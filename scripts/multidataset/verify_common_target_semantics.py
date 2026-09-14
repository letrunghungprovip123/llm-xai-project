#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.python.datasets.profile import load_dataset_profile


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify M10 target semantics on common IR/evidence outputs.")
    parser.add_argument("--dataset-profile", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()

    profile = load_dataset_profile(args.dataset_profile)
    semantics = profile.target.effective_prediction_semantics
    ir_path = args.workspace / "data/reports/explanation_ir_v3/explanation_ir_v3.jsonl"
    evidence_path = args.workspace / "data/reports/evidence_exposure/evidence_packages_all.jsonl"
    ir_records = _read_jsonl(ir_path)
    packages = _read_jsonl(evidence_path)

    failures: list[str] = []
    for index, record in enumerate(ir_records, start=1):
        target = record.get("target_semantics") or {}
        prediction = record.get("prediction_summary") or {}
        if target.get("positive_label") != semantics.positive_label:
            failures.append(f"IR {index}: positive_label mismatch")
        if target.get("negative_label") != semantics.negative_label:
            failures.append(f"IR {index}: negative_label mismatch")
        predicted_class = prediction.get("predicted_class")
        expected = semantics.positive_label if predicted_class == 1 else semantics.negative_label if predicted_class == 0 else None
        if expected is not None and prediction.get("predicted_label") != expected:
            failures.append(f"IR {index}: predicted_label does not match predicted_class")

    expected_package_count = len(ir_records) * 6
    if len(packages) != expected_package_count:
        failures.append(f"evidence package count {len(packages)} != expected {expected_package_count}")
    for index, package in enumerate(packages, start=1):
        prompt = package.get("prompt_payload") or {}
        target = prompt.get("target_semantics") or {}
        prediction = prompt.get("prediction") or {}
        if target.get("positive_label") != semantics.positive_label:
            failures.append(f"package {index}: prompt positive_label mismatch")
        if target.get("negative_label") != semantics.negative_label:
            failures.append(f"package {index}: prompt negative_label mismatch")
        if target.get("prediction_subject") != semantics.prediction_subject:
            failures.append(f"package {index}: prediction_subject mismatch")
        if "source_positive_value" in target or "source_negative_value" in target:
            failures.append(f"package {index}: source target values leaked into prompt semantics")
        predicted_class = prediction.get("predicted_class")
        expected = semantics.positive_label if predicted_class == 1 else semantics.negative_label if predicted_class == 0 else None
        if expected is not None and prediction.get("predicted_label") != expected:
            failures.append(f"package {index}: prediction label mismatch")

    if failures:
        for item in failures[:30]:
            print(f"FAIL {item}")
        if len(failures) > 30:
            print(f"... {len(failures) - 30} additional failures")
        print("COMMON_TARGET_SEMANTICS=FAIL")
        raise SystemExit(1)

    print(f"PASS dataset_id={profile.dataset_id}")
    print(f"PASS ir_records={len(ir_records)}")
    print(f"PASS evidence_packages={len(packages)}")
    print(f"PASS positive_label={semantics.positive_label}")
    print(f"PASS negative_label={semantics.negative_label}")
    print(f"PASS prediction_subject={semantics.prediction_subject}")
    print("PASS prompt_target_source_values_leaked=0")
    print("COMMON_TARGET_SEMANTICS=PASS")


if __name__ == "__main__":
    main()
