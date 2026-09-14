from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..common.hashing import sha256_file
from ..datasets.profile import load_canonical_bundle, load_dataset_profile
from ..datasets.receipts import StageReceipt, load_receipt, write_json_atomic
from .select_evaluation_subset import (
    LEVELS,
    TARGET_STRATA,
    build_case_rows,
    get_case_id,
    get_level,
    get_stratum,
    read_jsonl,
    select_balanced_cases,
    validate_case_matrix,
    write_jsonl,
    write_selected_case_csv,
)

EXPECTED_DATASET_ID = "freddie_sflld_2024"
DEFAULT_SEED = 20260711
DEFAULT_CASES_PER_STRATUM = 6


@dataclass(frozen=True)
class FreddieM16Result:
    receipt_path: Path
    receipt: StageReceipt
    subset_path: Path
    csv_path: Path
    manifest_path: Path
    selected_case_count: int
    selected_package_count: int


def build_and_certify_freddie_m16(
    *,
    workspace: Path,
    dataset_profile_path: Path,
    canonical_bundle_path: Path,
    m15_receipt_path: Path,
    seed: int = DEFAULT_SEED,
    cases_per_stratum: int = DEFAULT_CASES_PER_STRATUM,
) -> FreddieM16Result:
    workspace=workspace.expanduser().resolve(); profile_path=dataset_profile_path.expanduser().resolve(); bundle_path=canonical_bundle_path.expanduser().resolve(); m15_receipt_path=m15_receipt_path.expanduser().resolve()
    profile=load_dataset_profile(profile_path); bundle=load_canonical_bundle(bundle_path); m15=load_receipt(m15_receipt_path)
    if profile.dataset_id != EXPECTED_DATASET_ID or bundle.dataset_id != EXPECTED_DATASET_ID: raise ValueError("M16 requires Freddie dataset")
    if m15.stage != "freddie_evidence_m15" or m15.status != "PASS" or any(v != "PASS" for v in m15.invariants.values()): raise ValueError("M15 receipt not certified")
    if cases_per_stratum != 6: raise ValueError("Frozen replication protocol requires exactly 6 cases per stratum")

    input_path=workspace/"data/reports/evidence_exposure/evidence_packages_all.jsonl"
    if not input_path.is_file(): raise FileNotFoundError(input_path)
    records=read_jsonl(input_path); cases=validate_case_matrix(records); case_rows=build_case_rows(cases,seed); selected_rows=select_balanced_cases(case_rows,cases_per_stratum); selected_ids={row["case_id"] for row in selected_rows}
    expected_cases=len(TARGET_STRATA)*cases_per_stratum; expected_packages=expected_cases*len(LEVELS)
    if len(selected_ids) != expected_cases: raise RuntimeError(f"Expected {expected_cases} cases, got {len(selected_ids)}")
    selected_records=[record for record in records if get_case_id(record) in selected_ids]
    selected_records.sort(key=lambda r:(TARGET_STRATA.index(get_stratum(r) or ""),get_case_id(r),get_level(r)))
    if len(selected_records) != expected_packages: raise RuntimeError(f"Expected {expected_packages} packages, got {len(selected_records)}")

    # Dataset identity/semantics must be intact before experiment freeze.
    eff=profile.target.effective_prediction_semantics
    for record in selected_records:
        dataset=record.get("dataset") or {}; sem=record.get("target_semantics") or {}
        if dataset.get("dataset_id") != EXPECTED_DATASET_ID: raise RuntimeError("Selected package dataset identity mismatch")
        if sem.get("positive_label") != eff.positive_label or sem.get("negative_label") != eff.negative_label or sem.get("prediction_subject") != eff.prediction_subject: raise RuntimeError("Selected package target semantics mismatch")

    strata_counts={s:0 for s in TARGET_STRATA}; difficulty_counts={s:{"easy":0,"medium":0,"hard":0} for s in TARGET_STRATA}
    for row in selected_rows:
        strata_counts[row["stratum"]]+=1; difficulty_counts[row["stratum"]][row["difficulty_group"]]+=1
    if any(v != 6 for v in strata_counts.values()): raise RuntimeError(f"Strata are not exactly 6 each: {strata_counts}")
    if any(counts != {"easy":2,"medium":2,"hard":2} for counts in difficulty_counts.values()): raise RuntimeError(f"Difficulty balance mismatch: {difficulty_counts}")

    output_dir=workspace/"data/reports/evidence_exposure/evaluation_36"; output_dir.mkdir(parents=True,exist_ok=True)
    subset_path=output_dir/"evidence_packages_36.jsonl"; csv_path=output_dir/"selected_case_ids_36.csv"; manifest_path=output_dir/"selection_manifest_v2.json"
    write_jsonl(subset_path,selected_records); write_selected_case_csv(csv_path,selected_rows)
    manifest={
        "schema_version":"multidataset_evaluation_subset_manifest_v2","subset_id":"freddie_replication_36_v1","dataset_id":EXPECTED_DATASET_ID,"dataset_fingerprint":bundle.dataset_fingerprint,
        "source_input_path":str(input_path),"source_input_sha256":sha256_file(input_path),"selection_method":"deterministic stratified difficulty-balanced selection","seed":seed,"target_strata":TARGET_STRATA,
        "cases_per_stratum":cases_per_stratum,"difficulty_groups_per_stratum":{"easy":2,"medium":2,"hard":2},"selected_case_count":expected_cases,"selected_package_count":expected_packages,"evidence_levels":sorted(LEVELS),
        "subset_path":str(subset_path),"subset_sha256":sha256_file(subset_path),"selected_case_ids_csv":str(csv_path),"selection_performed_before_llm_generation":True,
    }
    write_json_atomic(manifest_path,manifest)
    receipt=StageReceipt(stage="freddie_evaluation_cohort_m16",stage_version="v1",dataset_id=EXPECTED_DATASET_ID,patch_id="0011",input_fingerprints={"m15_receipt":sha256_file(m15_receipt_path),"source_evidence_packages":sha256_file(input_path),"canonical_bundle":sha256_file(bundle_path)},config_fingerprints={"dataset_profile":sha256_file(profile_path)},output_fingerprints={str(p.relative_to(workspace)):sha256_file(p) for p in (subset_path,csv_path,manifest_path)},invariants={"selected_cases_36":"PASS","selected_packages_216":"PASS","six_per_stratum":"PASS","difficulty_balance_2_2_2":"PASS","dataset_identity":"PASS","target_semantics":"PASS"},status="PASS")
    receipt_path=workspace/"data/manifests/freddie_sflld_2024_m16_evaluation_cohort_receipt_v1.json"; write_json_atomic(receipt_path,receipt.to_dict())
    return FreddieM16Result(receipt_path,receipt,subset_path,csv_path,manifest_path,expected_cases,expected_packages)
