from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ..evidence_exposure.artifacts import build_quality_report
from ..evidence_exposure.package_builder import build_all_packages_for_ir
from .context import CommonXAIRunContext

LEVELS = ("S0", "S1", "S2", "S3", "S4", "S5")


@dataclass(frozen=True)
class CommonEvidenceResult:
    manifest_path: Path
    packages_path: Path
    package_count: int
    case_count: int
    quality_status: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    if not records:
        raise ValueError(f"No records in {path}")
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _augment_package(ctx: CommonXAIRunContext, package: dict[str, Any], ir: dict[str, Any]) -> dict[str, Any]:
    result = dict(package)
    level = str(result["evidence_level"])
    result["legacy_evidence_package_schema_version"] = result.get("evidence_package_schema_version")
    result["evidence_package_schema_version"] = "evidence_package_v2_multidataset"
    result["package_id"] = f"pkg::{ctx.profile.dataset_id}::{ctx.experiment_id}::{level}::{ir['ir_id']}"
    result["dataset"] = dict(ir["dataset"])
    result["experiment"] = dict(ir["experiment"])
    result["case"] = dict(ir["case"])
    result["target_semantics"] = ctx.profile.target.semantic_payload(
        include_source_values=True
    )
    prompt_payload = dict(result.get("prompt_payload") or {})
    prompt_payload["target_semantics"] = ctx.profile.target.semantic_payload(
        include_source_values=False
    )
    result["prompt_payload"] = prompt_payload
    result["internal_metadata"] = {
        "case": dict(ir["case"]),
        "ground_truth": result.get("internal_metadata", {}).get("ground_truth", {}),
        "dataset_id": ctx.profile.dataset_id,
        "experiment_id": ctx.experiment_id,
    }
    result.setdefault("audit_trace", {}).update(
        {
            "dataset_id": ctx.profile.dataset_id,
            "experiment_id": ctx.experiment_id,
            "canonical_case_id": ir["case"]["case_id"],
        }
    )
    return result


def run_common_evidence(ctx: CommonXAIRunContext) -> CommonEvidenceResult:
    if not ctx.profile.capabilities.supports_adaptive_evidence:
        raise ValueError("DatasetProfile declares supports_adaptive_evidence=false")
    ir_manifest = ctx.paths.manifest_dir / "common_explanation_ir_manifest_v3.json"
    if not ir_manifest.is_file():
        raise FileNotFoundError("Run common IR before common evidence")
    ir_path = ctx.paths.report_dir / "explanation_ir_v3" / "explanation_ir_v3.jsonl"
    ir_records = _read_jsonl(ir_path)
    packages: list[dict[str, Any]] = []
    for ir in ir_records:
        built = build_all_packages_for_ir(ir)
        packages.extend(_augment_package(ctx, item, ir) for item in built)
    expected = len(ir_records) * len(LEVELS)
    if len(packages) != expected:
        raise RuntimeError(f"Expected {expected} evidence packages, got {len(packages)}")
    ids = [str(item["package_id"]) for item in packages]
    if len(ids) != len(set(ids)):
        raise ValueError("Common evidence package identity collision detected")
    counts = pd.Series([item["evidence_level"] for item in packages]).value_counts().to_dict()
    for level in LEVELS:
        if int(counts.get(level, 0)) != len(ir_records):
            raise RuntimeError(f"Evidence level {level} count mismatch: {counts.get(level, 0)}")

    quality = build_quality_report(ir_records, packages)
    if str(quality.get("status")) == "FAILED":
        raise RuntimeError(f"Common evidence quality gate failed: {quality}")

    output_dir = ctx.paths.report_dir / "evidence_exposure"
    packages_path = output_dir / "evidence_packages_all.jsonl"
    summary_path = output_dir / "evidence_packages_summary.csv"
    quality_path = output_dir / "evidence_quality_report.json"
    _write_jsonl(packages_path, packages)
    pd.DataFrame(
        [
            {
                "package_id": item["package_id"],
                "source_ir_id": item["source_ir_id"],
                "dataset_id": item["dataset"]["dataset_id"],
                "experiment_id": item["experiment"]["experiment_id"],
                "case_id": item["case"]["case_id"],
                "case_type": item["case"]["case_type"],
                "evidence_level": item["evidence_level"],
                "selected_evidence_count": item.get("selection_metrics", {}).get("selected_evidence_count"),
                "coverage": item.get("selection_metrics", {}).get("coverage"),
                "coverage_status": item.get("selection_metrics", {}).get("coverage_status"),
            }
            for item in packages
        ]
    ).to_csv(summary_path, index=False)
    _write_json(quality_path, quality)
    manifest = {
        "schema_version": "common_evidence_exposure_manifest_v2",
        "created_at_utc": _utc_now(),
        **ctx.provenance(),
        "source_ir_schema_version": "explanation_ir_v3",
        "evidence_package_schema_version": "evidence_package_v2_multidataset",
        "case_count": len(ir_records),
        "package_count": len(packages),
        "level_counts": {level: int(counts.get(level, 0)) for level in LEVELS},
        "policy_invariants": {
            "S0_prediction_only": True,
            "S1_fixed_top10": True,
            "S2_semantic_enrichment_of_S1": True,
            "S3_adaptive_coverage_0_60": True,
            "S4_adaptive_coverage_0_70": True,
            "S5_s4_evidence_plus_backend_skeleton": True,
        },
        "quality_status": quality.get("status"),
        "outputs": {
            "packages_jsonl": str(packages_path),
            "summary_csv": str(summary_path),
            "quality_report": str(quality_path),
        },
        "status": "passed",
    }
    manifest_path = ctx.paths.manifest_dir / "common_evidence_exposure_manifest_v2.json"
    _write_json(manifest_path, manifest)
    return CommonEvidenceResult(
        manifest_path=manifest_path,
        packages_path=packages_path,
        package_count=len(packages),
        case_count=len(ir_records),
        quality_status=str(quality.get("status")),
    )
