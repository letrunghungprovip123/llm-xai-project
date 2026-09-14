#!/usr/bin/env python3
"""Render evidence-derived multi-dataset state; never mutates scientific state."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.python.datasets.receipts import load_receipt, sha256_path


def receipt_valid(path: Path, artifact_roots: list[Path] | None = None) -> tuple[bool, str]:
    if not path.is_file():
        return False, "receipt missing"
    artifact_roots = [path.parent] if artifact_roots is None else artifact_roots
    try:
        receipt = load_receipt(path)
        for name, expected in receipt.output_fingerprints.items():
            candidates = [root / name for root in artifact_roots]
            matches = [candidate for candidate in candidates if candidate.is_file()]
            if not matches:
                return False, f"output missing: {name}"
            if len(matches) > 1:
                return False, f"ambiguous output basename across evidence roots: {name}"
            if sha256_path(matches[0]) != expected:
                return False, f"output hash mismatch: {name}"
        if receipt.status != "PASS" or any(value != "PASS" for value in receipt.invariants.values()):
            return False, "receipt/invariant status is not PASS"
        return True, receipt.receipt_fingerprint
    except Exception as exc:
        return False, f"invalid receipt: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freddie-intake-dir", type=Path)
    parser.add_argument("--freddie-target-dir", type=Path)
    parser.add_argument("--freddie-artifact-root", type=Path)
    parser.add_argument("--freddie-ml-workspace", type=Path)
    parser.add_argument("--freddie-xai-workspace", type=Path)
    parser.add_argument("--freddie-evidence-workspace", type=Path)
    parser.add_argument("--freddie-evaluation-workspace", type=Path)
    parser.add_argument("--freddie-generation-workspace", type=Path)
    args = parser.parse_args()
    print("HOME_CREDIT M0-M10: LEGACY/COMMON VERIFIED OUTSIDE RECEIPT V1")

    m11_valid = False
    if args.freddie_intake_dir:
        path = args.freddie_intake_dir / "freddie_sflld_2024_m11_receipt_v1.json"
        m11_valid, detail = receipt_valid(path)
        print(f"FREDDIE M11: {'PASS' if m11_valid else 'PENDING'} evidence={detail}")
    else:
        print("FREDDIE M11: PENDING (provide --freddie-intake-dir)")

    m12a_valid = False
    if args.freddie_target_dir:
        path = args.freddie_target_dir / "freddie_sflld_2024_m12a_target_receipt_v1.json"
        m12a_valid, detail = receipt_valid(path)
        print(f"FREDDIE M12A TARGET: {'PASS' if m12a_valid else 'PENDING'} evidence={detail}")
    else:
        print("FREDDIE M12A TARGET: PENDING (provide --freddie-target-dir)")

    m12_valid = False
    if args.freddie_artifact_root:
        root = args.freddie_artifact_root.expanduser().resolve()
        receipt_path = root / "data/manifests/freddie_sflld_2024_m12_preparation_receipt_v1.json"
        evidence_roots = [root / "data/processed", root / "ml/registry", root / "data/manifests"]
        m12_valid, detail = receipt_valid(receipt_path, evidence_roots)
        print(f"FREDDIE M12 PREPARATION: {'PASS' if m12_valid else 'PENDING'} evidence={detail}")
    else:
        print("FREDDIE M12 PREPARATION: PENDING (provide --freddie-artifact-root)")

    m12_all = m11_valid and m12a_valid and m12_valid
    print(f"FREDDIE M12: {'PASS' if m12_all else 'PENDING'}")

    m13_valid = False
    if args.freddie_ml_workspace:
        root = args.freddie_ml_workspace.expanduser().resolve()
        receipt_path = root / "data/manifests/freddie_sflld_2024_m13_common_ml_receipt_v1.json"
        m13_valid, detail = receipt_valid(receipt_path, [root])
        if not m12_all:
            m13_valid = False
            detail = "upstream M12 is not PASS"
        print(f"FREDDIE M13: {'PASS' if m13_valid else 'PENDING'} evidence={detail}")
    else:
        print("FREDDIE M13: PENDING (provide --freddie-ml-workspace)")
    m14_valid = False
    if args.freddie_xai_workspace:
        root = args.freddie_xai_workspace.expanduser().resolve()
        receipt_path = root / "data/manifests/freddie_sflld_2024_m14_xai_ir_receipt_v1.json"
        m14_valid, detail = receipt_valid(receipt_path, [root])
        if not m13_valid:
            m14_valid = False
            detail = "upstream M13 is not PASS"
        print(f"FREDDIE M14: {'PASS' if m14_valid else 'PENDING'} evidence={detail}")
    else:
        print("FREDDIE M14: PENDING (provide --freddie-xai-workspace)")
    m15_valid = False
    if args.freddie_evidence_workspace:
        root = args.freddie_evidence_workspace.expanduser().resolve()
        receipt_path = root / "data/manifests/freddie_sflld_2024_m15_evidence_receipt_v1.json"
        m15_valid, detail = receipt_valid(receipt_path, [root])
        if not m14_valid:
            m15_valid = False
            detail = "upstream M14 is not PASS"
        print(f"FREDDIE M15: {'PASS' if m15_valid else 'PENDING'} evidence={detail}")
    else:
        print("FREDDIE M15: PENDING (provide --freddie-evidence-workspace)")
    m16_valid = False
    if args.freddie_evaluation_workspace:
        root = args.freddie_evaluation_workspace.expanduser().resolve()
        receipt_path = root / "data/manifests/freddie_sflld_2024_m16_evaluation_cohort_receipt_v1.json"
        m16_valid, detail = receipt_valid(receipt_path, [root])
        if not m15_valid:
            m16_valid = False
            detail = "upstream M15 is not PASS"
        print(f"FREDDIE M16: {'PASS' if m16_valid else 'PENDING'} evidence={detail}")
    else:
        print("FREDDIE M16: PENDING (provide --freddie-evaluation-workspace)")
    m17a_valid = False
    if args.freddie_generation_workspace:
        root = args.freddie_generation_workspace.expanduser().resolve()
        receipt_path = root / "data/manifests/freddie_sflld_2024_m17a_generation_receipt_v1.json"
        m17a_valid, detail = receipt_valid(receipt_path, [root])
        if not m16_valid:
            m17a_valid = False
            detail = "upstream M16 is not PASS"
        print(f"FREDDIE M17A: {'PASS' if m17a_valid else 'PENDING'} evidence={detail}")
    else:
        print("FREDDIE M17A: PENDING (provide --freddie-generation-workspace)")
    print("FREDDIE M17B-M19: PENDING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
