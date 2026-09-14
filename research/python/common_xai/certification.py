from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.hashing import sha256_file
from ..datasets.profile import load_canonical_bundle, load_dataset_profile
from ..datasets.receipts import StageReceipt, load_receipt, write_json_atomic
from .context import CommonXAIRunContext
from .xai_stage import CASE_GROUPS, _load_inputs, select_common_cases

EXPECTED_DATASET_ID = "freddie_sflld_2024"
EXPECTED_CASES_PER_GROUP = 20
EXPECTED_CASE_COUNT = len(CASE_GROUPS) * EXPECTED_CASES_PER_GROUP


@dataclass(frozen=True)
class FreddieM14Certification:
    receipt_path: Path
    receipt: StageReceipt
    summary: dict[str, Any]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def _require(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def preflight_freddie_case_selection(ctx: CommonXAIRunContext, cases_per_group: int = EXPECTED_CASES_PER_GROUP) -> dict[str, Any]:
    inputs, _, _ = _load_inputs(ctx)
    selected, counts, warnings = select_common_cases(
        ctx=ctx,
        model_bundle=inputs.model_bundle,
        predictions=inputs.predictions,
        cases_per_group=cases_per_group,
    )
    expected = cases_per_group * len(CASE_GROUPS)
    status = "PASS" if len(selected) == expected and all(counts.get(group) == cases_per_group for group in CASE_GROUPS) and not warnings else "FAIL"
    return {
        "status": status,
        "threshold": float(selected["threshold"].iloc[0]) if not selected.empty else None,
        "selected_count": int(len(selected)),
        "expected_count": int(expected),
        "group_counts": {group: int(counts.get(group, 0)) for group in CASE_GROUPS},
        "warnings": list(warnings),
        "selected_case_ids": selected["case_id"].astype(str).tolist() if "case_id" in selected else [],
    }


def certify_freddie_m14(
    *,
    workspace: Path,
    dataset_profile_path: Path,
    canonical_bundle_path: Path,
    m13_receipt_path: Path,
    expected_cases_per_group: int = EXPECTED_CASES_PER_GROUP,
    write_receipt: bool = True,
) -> FreddieM14Certification:
    workspace = workspace.expanduser().resolve()
    profile_path = dataset_profile_path.expanduser().resolve()
    bundle_path = canonical_bundle_path.expanduser().resolve()
    m13_receipt_path = m13_receipt_path.expanduser().resolve()
    profile = load_dataset_profile(profile_path)
    bundle = load_canonical_bundle(bundle_path)
    m13 = load_receipt(_require(m13_receipt_path))
    if profile.dataset_id != EXPECTED_DATASET_ID or bundle.dataset_id != EXPECTED_DATASET_ID:
        raise ValueError("M14 certification requires freddie_sflld_2024")
    if m13.dataset_id != EXPECTED_DATASET_ID or m13.stage != "freddie_common_ml_m13" or m13.status != "PASS":
        raise ValueError("M13 receipt is not a certified Freddie M13 receipt")
    if any(value != "PASS" for value in m13.invariants.values()):
        raise ValueError("M13 receipt has non-PASS invariant")

    manifest_dir = workspace / "data/manifests"
    xai_dir = workspace / "data/reports/xai"
    quality_dir = workspace / "data/reports/xai_quality"
    ir_dir = workspace / "data/reports/explanation_ir_v3"
    xai_manifest_path = _require(manifest_dir / "common_xai_manifest.json")
    ir_manifest_path = _require(manifest_dir / "common_explanation_ir_manifest_v3.json")
    selected_path = _require(xai_dir / "xai_selected_cases.csv")
    evidence_path = _require(xai_dir / "xai_local_evidence.jsonl")
    quality_path = _require(quality_dir / "xai_evidence_quality_summary.csv")
    ir_path = _require(ir_dir / "explanation_ir_v3.jsonl")
    ir_summary_path = _require(ir_dir / "explanation_ir_v3_summary.csv")

    xai_manifest = _load_json(xai_manifest_path)
    ir_manifest = _load_json(ir_manifest_path)
    selected = pd.read_csv(selected_path)
    quality = pd.read_csv(quality_path)
    evidence = _load_jsonl(evidence_path)
    ir_records = _load_jsonl(ir_path)
    expected_case_count = len(CASE_GROUPS) * expected_cases_per_group

    invariants: dict[str, str] = {}
    failures: list[str] = []
    def check(name: str, condition: bool, detail: str) -> None:
        invariants[name] = "PASS" if condition else "FAIL"
        if not condition:
            failures.append(f"{name}: {detail}")

    for name, payload in (("xai", xai_manifest), ("ir", ir_manifest)):
        check(f"{name}_dataset_id", payload.get("dataset_id") == EXPECTED_DATASET_ID, str(payload.get("dataset_id")))
        check(f"{name}_dataset_fingerprint", payload.get("dataset_fingerprint") == bundle.dataset_fingerprint, str(payload.get("dataset_fingerprint")))

    case_selection = xai_manifest.get("case_selection", {})
    counts = case_selection.get("group_counts", {})
    check("case_count_120", int(xai_manifest.get("case_count", -1)) == expected_case_count, str(xai_manifest.get("case_count")))
    check("selected_csv_count", len(selected) == expected_case_count, str(len(selected)))
    check("selected_case_unique", selected["case_id"].astype(str).nunique() == expected_case_count, "duplicate case_id")
    check("case_groups_exact", all(int(counts.get(group, -1)) == expected_cases_per_group for group in CASE_GROUPS), str(counts))
    check("selection_warnings_empty", not case_selection.get("warnings"), str(case_selection.get("warnings")))
    check("threshold_frozen_0_5", selected["threshold"].nunique() == 1 and float(selected["threshold"].iloc[0]) == 0.5, str(selected["threshold"].unique()[:5]))
    check("additivity_failed_zero", int(xai_manifest.get("additivity", {}).get("failed_count", -1)) == 0, str(xai_manifest.get("additivity")))
    check("quality_rows", len(quality) == expected_case_count, str(len(quality)))
    check("quality_finite", quality[["top10_coverage", "comprehensiveness_top10", "sufficiency_drop_top10"]].notna().all().all(), "non-finite quality")
    check("unknown_feature_group_zero", abs(float(quality["unknown_feature_group_abs_share"].mean())) <= 1e-12, str(quality["unknown_feature_group_abs_share"].mean()))
    check("local_evidence_count", len(evidence) == expected_case_count, str(len(evidence)))

    check("ir_record_count", int(ir_manifest.get("record_count", -1)) == expected_case_count and len(ir_records) == expected_case_count, f"manifest={ir_manifest.get('record_count')} file={len(ir_records)}")
    ir_ids = [str(item.get("ir_id")) for item in ir_records]
    ir_case_ids = [str((item.get("case") or {}).get("case_id")) for item in ir_records]
    check("ir_identity_unique", len(set(ir_ids)) == expected_case_count and len(set(ir_case_ids)) == expected_case_count, "IR/case identity collision")
    semantic_ok = True
    for item in ir_records:
        semantics = item.get("target_semantics") or {}
        if semantics.get("positive_label") != profile.target.effective_prediction_semantics.positive_label:
            semantic_ok = False
            break
        if semantics.get("negative_label") != profile.target.effective_prediction_semantics.negative_label:
            semantic_ok = False
            break
        if semantics.get("prediction_subject") != profile.target.effective_prediction_semantics.prediction_subject:
            semantic_ok = False
            break
    check("ir_target_semantics", semantic_ok, "Freddie target semantics missing/mismatched")

    if failures:
        raise RuntimeError("Freddie M14 certification failed: " + "; ".join(failures))

    output_paths = [xai_manifest_path, ir_manifest_path, selected_path, evidence_path, quality_path, ir_path, ir_summary_path]
    output_hashes = {str(path.relative_to(workspace)): sha256_file(path) for path in output_paths}
    receipt = StageReceipt(
        stage="freddie_xai_ir_m14",
        stage_version="v1",
        dataset_id=EXPECTED_DATASET_ID,
        patch_id="0009",
        input_fingerprints={"m13_receipt": sha256_file(m13_receipt_path), "canonical_bundle": sha256_file(bundle_path)},
        config_fingerprints={"dataset_profile": sha256_file(profile_path)},
        output_fingerprints=output_hashes,
        invariants=invariants,
        status="PASS",
    )
    receipt_path = manifest_dir / "freddie_sflld_2024_m14_xai_ir_receipt_v1.json"
    if write_receipt:
        write_json_atomic(receipt_path, receipt.to_dict())
    return FreddieM14Certification(
        receipt_path=receipt_path,
        receipt=receipt,
        summary={
            "case_count": expected_case_count,
            "feature_count": int(xai_manifest.get("feature_count", -1)),
            "explainer_type": str(xai_manifest.get("explainer_type", "")),
            "ir_warnings": int(ir_manifest.get("warning_count", 0)),
            "receipt_fingerprint": receipt.receipt_fingerprint,
        },
    )
