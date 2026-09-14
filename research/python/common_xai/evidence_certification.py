from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..common.hashing import sha256_file
from ..datasets.profile import load_canonical_bundle, load_dataset_profile
from ..datasets.receipts import StageReceipt, load_receipt, write_json_atomic

LEVELS = ("S0", "S1", "S2", "S3", "S4", "S5")
SEMANTIC_LEVELS = frozenset({"S2", "S3", "S4", "S5"})
UNKNOWN_CONCEPT_TOKENS = frozenset({"", "unknown", "none", "unknown_feature_group", "unknown_concept"})
EXPECTED_DATASET_ID = "freddie_sflld_2024"


@dataclass(frozen=True)
class EvidenceSeparabilityReport:
    case_count: int
    package_count: int
    s1_s3_equal_rate: float
    s3_s4_equal_rate: float
    s1_s4_equal_rate: float
    unknown_concept_rate: float
    semantic_item_count: int
    semantic_unknown_concept_count: int
    s1_raw_item_count: int
    s1_concept_exposure_count: int
    status: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class FreddieM15Certification:
    receipt_path: Path
    receipt: StageReceipt
    report_path: Path
    report: EvidenceSeparabilityReport


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records=[]
    with path.open("r",encoding="utf-8") as h:
        for line in h:
            if line.strip(): records.append(json.loads(line))
    return records


def _ids(package: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(item.get("feature_id")) for item in (package.get("selected_evidence") or []))


def analyze_evidence_packages(packages: list[dict[str, Any]]) -> EvidenceSeparabilityReport:
    by_case: dict[str, dict[str, dict[str, Any]]] = {}
    semantic_unknown=0; semantic_total=0; s1_raw_items=0; s1_concept_exposure=0
    for package in packages:
        case = package.get("case") or {}
        case_id = str(case.get("case_id") or package.get("source_ir_id") or "")
        level = str(package.get("evidence_level", ""))
        if not case_id or level not in LEVELS: raise ValueError("Evidence package missing case identity or valid S0-S5 level")
        if level in by_case.setdefault(case_id, {}): raise ValueError(f"Duplicate evidence level for {case_id}: {level}")
        by_case[case_id][level]=package
        for item in package.get("selected_evidence") or []:
            # S1 is intentionally raw SHAP evidence. Its package builder strips
            # concept/semantic metadata by design, so absence of a concept in S1
            # is NOT an unresolved semantic mapping. Semantic coverage is only
            # meaningful for levels that are contractually semantic (S2-S5).
            if level == "S1":
                s1_raw_items += 1
                concept_value = item.get("concept") or item.get("concept_id")
                if concept_value is not None and str(concept_value).strip().lower() not in UNKNOWN_CONCEPT_TOKENS:
                    s1_concept_exposure += 1
            elif level in SEMANTIC_LEVELS:
                semantic_total += 1
                concept_value = item.get("concept") or item.get("concept_id") or "unknown_feature_group"
                if str(concept_value).strip().lower() in UNKNOWN_CONCEPT_TOKENS:
                    semantic_unknown += 1
    failures=[]; warnings=[]; eq13=eq34=eq14=0
    for case_id, levels in by_case.items():
        missing=set(LEVELS)-set(levels)
        if missing: failures.append(f"{case_id}: missing {sorted(missing)}"); continue
        s0,s1,s2,s3,s4,s5=(levels[x] for x in LEVELS)
        ids0,ids1,ids2,ids3,ids4,ids5=map(_ids,(s0,s1,s2,s3,s4,s5))
        if ids0: failures.append(f"{case_id}: S0 contains feature evidence")
        if ids1 != ids2: failures.append(f"{case_id}: S1/S2 feature identity differs")
        if not (3 <= len(ids3) <= 10): failures.append(f"{case_id}: S3 k={len(ids3)} outside 3..10")
        if not (5 <= len(ids4) <= 20): failures.append(f"{case_id}: S4 k={len(ids4)} outside 5..20")
        if ids4 != ids5: failures.append(f"{case_id}: S4/S5 feature identity differs")
        if set(ids1)==set(ids3): eq13+=1
        if set(ids3)==set(ids4): eq34+=1
        if set(ids1)==set(ids4): eq14+=1
        for package in levels.values():
            prompt_sem=(package.get("prompt_payload") or {}).get("target_semantics") or {}
            if "source_positive_value" in prompt_sem or "source_negative_value" in prompt_sem:
                failures.append(f"{case_id}: source target values leaked into prompt")
    if failures: raise RuntimeError("Evidence structural invariants failed: " + "; ".join(failures[:20]))
    n=len(by_case)
    rates={"S1_S3": eq13/n if n else 1.0, "S3_S4": eq34/n if n else 1.0, "S1_S4": eq14/n if n else 1.0}
    status="PASS"
    for label,rate in rates.items():
        if rate > 0.90: status="FAIL"; warnings.append(f"{label} exact-set equality {rate:.3f} > 0.90")
        elif rate >= 0.50 and status != "FAIL": status="REVIEW_REQUIRED"; warnings.append(f"{label} exact-set equality {rate:.3f} in 0.50..0.90")
    if s1_concept_exposure:
        status="FAIL"
        warnings.append(f"S1 unexpectedly exposes concept metadata on {s1_concept_exposure}/{s1_raw_items} raw evidence items")
    unknown_rate=semantic_unknown/semantic_total if semantic_total else 0.0
    if unknown_rate > 0.05: status="FAIL"; warnings.append(f"semantic unknown concept rate {unknown_rate:.3f} > 0.05")
    elif unknown_rate > 0 and status == "PASS": status="REVIEW_REQUIRED"; warnings.append(f"semantic unknown concept rate {unknown_rate:.3f} > 0")
    return EvidenceSeparabilityReport(
        n, len(packages), rates["S1_S3"], rates["S3_S4"], rates["S1_S4"],
        unknown_rate, semantic_total, semantic_unknown, s1_raw_items, s1_concept_exposure,
        status, tuple(warnings),
    )


def certify_freddie_m15(*, workspace: Path, dataset_profile_path: Path, canonical_bundle_path: Path, m14_receipt_path: Path, write_receipt: bool=True) -> FreddieM15Certification:
    workspace=workspace.expanduser().resolve(); profile_path=dataset_profile_path.expanduser().resolve(); bundle_path=canonical_bundle_path.expanduser().resolve(); m14_receipt_path=m14_receipt_path.expanduser().resolve()
    profile=load_dataset_profile(profile_path); bundle=load_canonical_bundle(bundle_path); m14=load_receipt(m14_receipt_path)
    if profile.dataset_id != EXPECTED_DATASET_ID or bundle.dataset_id != EXPECTED_DATASET_ID: raise ValueError("M15 requires Freddie dataset")
    if m14.stage != "freddie_xai_ir_m14" or m14.status != "PASS" or any(v != "PASS" for v in m14.invariants.values()): raise ValueError("M14 receipt not certified")
    manifest_dir=workspace/"data/manifests"; evidence_dir=workspace/"data/reports/evidence_exposure"
    manifest_path=manifest_dir/"common_evidence_exposure_manifest_v2.json"; packages_path=evidence_dir/"evidence_packages_all.jsonl"; quality_path=evidence_dir/"evidence_quality_report.json"; summary_path=evidence_dir/"evidence_packages_summary.csv"
    for p in (manifest_path,packages_path,quality_path,summary_path):
        if not p.is_file(): raise FileNotFoundError(p)
    manifest=json.loads(manifest_path.read_text()); packages=_read_jsonl(packages_path); quality=json.loads(quality_path.read_text())
    if manifest.get("dataset_id") != EXPECTED_DATASET_ID or manifest.get("dataset_fingerprint") != bundle.dataset_fingerprint: raise RuntimeError("Evidence manifest dataset identity mismatch")
    report=analyze_evidence_packages(packages)
    if report.case_count != 120 or report.package_count != 720: raise RuntimeError(f"Expected 120 cases/720 packages, got {report.case_count}/{report.package_count}")
    if report.status != "PASS": raise RuntimeError("EVIDENCE_CONDITION_SEPARABILITY=" + report.status + " " + "; ".join(report.warnings))
    # Ensure target semantics on every package match Freddie profile.
    eff=profile.target.effective_prediction_semantics
    for package in packages:
        sem=package.get("target_semantics") or {}
        if sem.get("positive_label") != eff.positive_label or sem.get("negative_label") != eff.negative_label or sem.get("prediction_subject") != eff.prediction_subject:
            raise RuntimeError("Evidence target semantics mismatch")
    report_payload={
        "schema_version":"freddie_evidence_separability_report_v2", "dataset_id":EXPECTED_DATASET_ID, "dataset_fingerprint":bundle.dataset_fingerprint,
        "case_count":report.case_count,"package_count":report.package_count,"exact_set_equality":{"S1_S3":report.s1_s3_equal_rate,"S3_S4":report.s3_s4_equal_rate,"S1_S4":report.s1_s4_equal_rate},
        "unknown_concept_rate":report.unknown_concept_rate,
        "semantic_item_count":report.semantic_item_count,
        "semantic_unknown_concept_count":report.semantic_unknown_concept_count,
        "s1_raw_item_count":report.s1_raw_item_count,
        "s1_concept_exposure_count":report.s1_concept_exposure_count,
        "semantic_coverage_scope":"S2-S5_only; S1_is_intentionally_raw",
        "status":report.status,"warnings":list(report.warnings),
        "thresholds":{"hard_fail_exact_equality_gt":0.90,"review_exact_equality_gte":0.50,"semantic_unknown_concept_hard_fail_gt":0.05},
    }
    report_path=evidence_dir/"freddie_evidence_separability_report_v1.json"; write_json_atomic(report_path,report_payload)
    outputs=[manifest_path,packages_path,quality_path,summary_path,report_path]
    receipt=StageReceipt(stage="freddie_evidence_m15",stage_version="v1.1",dataset_id=EXPECTED_DATASET_ID,patch_id="0010a",input_fingerprints={"m14_receipt":sha256_file(m14_receipt_path),"canonical_bundle":sha256_file(bundle_path)},config_fingerprints={"dataset_profile":sha256_file(profile_path)},output_fingerprints={str(p.relative_to(workspace)):sha256_file(p) for p in outputs},invariants={"evidence_120x6":"PASS","structural_s0_s5":"PASS","condition_separability":"PASS","target_semantics":"PASS"},status="PASS")
    receipt_path=manifest_dir/"freddie_sflld_2024_m15_evidence_receipt_v1.json"
    if write_receipt: write_json_atomic(receipt_path,receipt.to_dict())
    return FreddieM15Certification(receipt_path,receipt,report_path,report)
