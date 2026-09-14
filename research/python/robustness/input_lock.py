from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .common import (
    claim_types,
    derive_complete_case_ids,
    option_ids,
    read_json,
    record_file,
    resolve_record,
)


def _certified_json(path: Path, *, gate: str | None = None) -> dict[str, Any]:
    value = read_json(path)
    if gate is not None and value.get("gate") != gate and value.get("exit_gate") != gate:
        raise ValueError(f"Expected certified gate {gate}: {path}")
    if "passed" in value and value.get("passed") is not True:
        raise ValueError(f"Validation is not passed: {path}")
    return value


def _sibling_csv(source_record: dict[str, Any], root: Path, name: str) -> Path:
    path = resolve_record(root, source_record, name + "_anchor")
    sibling = path.parent / name
    if not sibling.is_file():
        raise FileNotFoundError(sibling)
    return sibling


def _readiness(root: Path, home_credit_metrics: Path, freddie_metrics: Path) -> dict[str, Any]:
    hc_analysis = home_credit_metrics.parent.parent
    fm_analysis = freddie_metrics.parent.parent
    validator_paths = [
        hc_analysis / "validator_sensitivity" / "validator_sensitivity_validation.json",
        fm_analysis / "validator_sensitivity" / "validator_sensitivity_validation.json",
    ]
    validator_ready = all(p.is_file() for p in validator_paths)
    template_paths = [
        hc_analysis / "template_baseline" / "template_baseline_manifest.json",
        fm_analysis / "template_baseline" / "template_baseline_manifest.json",
    ]
    template_ready = all(p.is_file() for p in template_paths)
    return {
        "validator_sensitivity": {
            "status": "READY" if validator_ready else "NOT_AVAILABLE",
            "reason": None if validator_ready else "Comparable certified alternative-validator outputs are not present for both datasets.",
        },
        "template_baseline": {
            "status": "READY" if template_ready else "NOT_READY",
            "reason": None if template_ready else "Certified common-renderer template outputs are not present for both datasets.",
        },
        "human_calibration": {
            "status": "NOT_PERFORMED",
            "reason": "No adjudicated multi-dataset human-calibration release is an M27 parent.",
        },
    }


def build_input_lock(
    root: Path,
    protocol_path: Path,
    m25_lock_path: Path,
    m25_dir: Path,
    m26_policy_lock_path: Path,
    m26_dir: Path,
) -> dict[str, Any]:
    protocol = read_json(protocol_path)
    if protocol.get("status") != "FROZEN_BEFORE_ROBUSTNESS_EXECUTION":
        raise ValueError("M27 protocol is not frozen.")
    if protocol.get("provider_execution_allowed") is not False:
        raise ValueError("M27 provider execution must be disabled.")

    m25_lock = _certified_json(m25_lock_path, gate="MULTIDATASET_REPLICATION_INPUT_LOCK_READY")
    m25_manifest_path = m25_dir / "replication_manifest.json"
    m25_validation_path = m25_dir / "replication_validation.json"
    _certified_json(m25_manifest_path, gate="MULTIDATASET_REPLICATION_READY")
    _certified_json(m25_validation_path, gate="MULTIDATASET_REPLICATION_READY")

    m26_policy_lock = _certified_json(m26_policy_lock_path, gate="MULTIDATASET_DECISION_POLICY_LOCK_READY")
    m26_manifest_path = m26_dir / "decision_manifest.json"
    m26_validation_path = m26_dir / "decision_validation.json"
    _certified_json(m26_manifest_path, gate="MULTIDATASET_DECISION_READY")
    _certified_json(m26_validation_path, gate="MULTIDATASET_DECISION_READY")

    hc_metrics_path = resolve_record(root, m25_lock["inputs"]["home_credit_generation_metrics"], "home_credit_generation_metrics")
    fm_metrics_path = resolve_record(root, m25_lock["inputs"]["freddie_generation_metrics"], "freddie_generation_metrics")
    hc_claims_path = _sibling_csv(m25_lock["inputs"]["home_credit_generation_diagnostics"], root, "claim_diagnostics.csv")
    fm_claims_path = _sibling_csv(m25_lock["inputs"]["freddie_generation_diagnostics"], root, "claim_diagnostics.csv")
    hc_metrics = pd.read_csv(hc_metrics_path, low_memory=False)
    fm_metrics = pd.read_csv(fm_metrics_path, low_memory=False)
    hc_claims = pd.read_csv(hc_claims_path, low_memory=False)
    fm_claims = pd.read_csv(fm_claims_path, low_memory=False)

    if len(hc_metrics) != 648 or len(fm_metrics) != 648:
        raise ValueError("M27 requires 648 generation rows per dataset.")
    if option_ids(hc_metrics) != option_ids(fm_metrics) or len(option_ids(hc_metrics)) != 18:
        raise ValueError("M27 requires the same 18 options in both datasets.")

    hc_complete = derive_complete_case_ids(hc_metrics)
    fm_complete = derive_complete_case_ids(fm_metrics)

    margins = [float(x["margin"]) for x in protocol["noninferiority_margin_lanes"]]
    primary_margins = [float(x["margin"]) for x in protocol["noninferiority_margin_lanes"] if x["analysis_status"] == "PRIMARY_CERTIFIED"]
    if margins != [0.02, 0.03, 0.05] or primary_margins != [0.03]:
        raise ValueError("M27 margin registry drift.")
    bootstrap = protocol["bootstrap_sensitivity"]
    if bootstrap.get("resampling_unit") != "canonical_case" or bootstrap.get("claim_resampling_allowed") is not False:
        raise ValueError("M27 bootstrap must resample canonical cases, never claims.")

    inputs = {
        "home_credit_generation_metrics": record_file(root, hc_metrics_path, rows=len(hc_metrics)),
        "freddie_generation_metrics": record_file(root, fm_metrics_path, rows=len(fm_metrics)),
        "home_credit_claim_diagnostics": record_file(root, hc_claims_path, rows=len(hc_claims)),
        "freddie_claim_diagnostics": record_file(root, fm_claims_path, rows=len(fm_claims)),
        "m25_contrast_concordance": record_file(root, m25_dir / "contrast_concordance.csv"),
        "m25_rank_stability": record_file(root, m25_dir / "rank_stability.csv"),
        "m26_noninferiority_results": record_file(root, m26_dir / "noninferiority_results.csv"),
        "m26_dataset_option_assessment": record_file(root, m26_dir / "dataset_option_assessment.csv"),
        "m26_recommendations": record_file(root, m26_dir / "recommendations.csv"),
        "m26_scenario_options": record_file(root, m26_dir / "scenario_options.csv"),
    }
    return {
        "schema_version": "multidataset_robustness_input_lock_v1",
        "protocol_id": protocol["protocol_id"],
        "producer": "M27A_0032",
        "protocol": record_file(root, protocol_path),
        "parents": {
            "m25_input_lock": record_file(root, m25_lock_path),
            "m25_manifest": record_file(root, m25_manifest_path),
            "m25_validation": record_file(root, m25_validation_path),
            "m26_policy_lock": record_file(root, m26_policy_lock_path),
            "m26_manifest": record_file(root, m26_manifest_path),
            "m26_validation": record_file(root, m26_validation_path),
        },
        "inputs": inputs,
        "observed": {
            "datasets": ["home_credit_default_risk", "freddie_sflld_2024"],
            "options": 18,
            "home_credit_complete_case_count": len(hc_complete),
            "home_credit_complete_case_ids": hc_complete,
            "freddie_complete_case_count": len(fm_complete),
            "freddie_complete_case_ids": fm_complete,
            "home_credit_claim_types": claim_types(hc_claims),
            "freddie_claim_types": claim_types(fm_claims),
        },
        "readiness": _readiness(root, hc_metrics_path, fm_metrics_path),
        "provider_execution_allowed": False,
        "gate": "MULTIDATASET_ROBUSTNESS_INPUT_LOCK_READY",
    }
