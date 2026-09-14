from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ..explanation_ir.ir_builder import build_explanation_ir_records
from .context import CommonXAIRunContext


@dataclass(frozen=True)
class CommonIRResult:
    manifest_path: Path
    ir_path: Path
    summary_path: Path
    record_count: int
    warning_count: int


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


def _augment_ir_v3(ctx: CommonXAIRunContext, ir: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    case = dict(source.get("case") or {})
    evidence_id = str(source["evidence_id"])
    ir_id = f"ir::{ctx.profile.dataset_id}::{ctx.experiment_id}::{evidence_id}"
    trace_id = f"trace::{ctx.profile.dataset_id}::{ctx.experiment_id}::{evidence_id}"
    result = dict(ir)
    result["legacy_ir_schema_version"] = ir.get("ir_schema_version")
    result["ir_schema_version"] = "explanation_ir_v3"
    result["ir_id"] = ir_id
    result["trace_id"] = trace_id
    result["dataset"] = {
        "dataset_id": ctx.profile.dataset_id,
        "dataset_version": ctx.profile.dataset_version,
        "dataset_fingerprint": ctx.bundle.dataset_fingerprint,
        "domain": ctx.profile.domain,
        "task_type": ctx.profile.task_type,
    }
    result["experiment"] = {
        "experiment_id": ctx.experiment_id,
        "run_id": ctx.run_id,
        "source_common_ml_run_id": ctx.source_run_id,
    }
    result["case"] = {
        "case_id": str(case.get("case_id")),
        "source_entity_id": str(case.get("source_entity_id")),
        "entity_type": str(case.get("entity_type") or ctx.profile.entity.entity_type),
        "row_index": case.get("row_index"),
        "case_type": case.get("case_type"),
        "selection_rank": case.get("selection_rank"),
    }
    result["target_semantics"] = ctx.profile.target.semantic_payload(
        include_source_values=True
    )
    prediction = dict(result.get("prediction_summary") or {})
    predicted_class = prediction.get("predicted_class")
    if predicted_class in (1, 1.0, True):
        prediction["predicted_label"] = (
            ctx.profile.target.effective_prediction_semantics.positive_label
        )
        prediction["predicted_label_display"] = (
            ctx.profile.target.effective_prediction_semantics.positive_display_name
        )
    elif predicted_class in (0, 0.0, False):
        prediction["predicted_label"] = (
            ctx.profile.target.effective_prediction_semantics.negative_label
        )
        prediction["predicted_label_display"] = (
            ctx.profile.target.effective_prediction_semantics.negative_display_name
        )
    result["prediction_summary"] = prediction
    result["customer"] = {
        "case_id": result["case"]["case_id"],
        "source_entity_id": result["case"]["source_entity_id"],
        "entity_type": result["case"]["entity_type"],
        "row_index": result["case"]["row_index"],
        "case_type": result["case"]["case_type"],
        "selection_rank": result["case"]["selection_rank"],
    }
    result.setdefault("evidence_trace", {}).update(
        {
            "dataset_id": ctx.profile.dataset_id,
            "dataset_fingerprint": ctx.bundle.dataset_fingerprint,
            "experiment_id": ctx.experiment_id,
            "canonical_case_id": result["case"]["case_id"],
            "source_entity_id": result["case"]["source_entity_id"],
        }
    )
    result.setdefault("metadata", {}).update(
        {
            "builder_version": "common_ir_v3",
            "legacy_builder_version": ir.get("metadata", {}).get("builder_version"),
            "dataset_id": ctx.profile.dataset_id,
            "experiment_id": ctx.experiment_id,
            "canonical_case_id": result["case"]["case_id"],
        }
    )
    return result


def run_common_ir(ctx: CommonXAIRunContext) -> CommonIRResult:
    xai_manifest = ctx.paths.manifest_dir / "common_xai_manifest.json"
    if not xai_manifest.is_file():
        raise FileNotFoundError("Run common XAI before common IR")
    evidence_path = ctx.paths.report_dir / "xai" / "xai_local_evidence.jsonl"
    quality_path = ctx.paths.report_dir / "xai_quality" / "xai_evidence_quality_summary.csv"
    concept_path = ctx.paths.report_dir / "xai_quality" / "xai_concept_aggregation_report.csv"
    source_records = _read_jsonl(evidence_path)
    quality_df = pd.read_csv(quality_path)
    concepts_df = pd.read_csv(concept_path)
    quality_by_id = {str(row["evidence_id"]): row.to_dict() for _, row in quality_df.iterrows()}
    concepts_by_id: dict[str, list[dict[str, Any]]] = {}
    for _, row in concepts_df.iterrows():
        concepts_by_id.setdefault(str(row["evidence_id"]), []).append(row.to_dict())

    built = build_explanation_ir_records(
        evidence_records=source_records,
        run_mode="evaluation",
        has_ground_truth=True,
        source_file=evidence_path,
        quality_by_evidence_id=quality_by_id,
        concepts_by_evidence_id=concepts_by_id,
    )
    if built.errors:
        raise RuntimeError(f"Common IR builder errors: {built.errors[:10]}")
    if len(built.ir_records) != len(source_records):
        raise RuntimeError("Common IR record count differs from common XAI evidence count")
    source_by_id = {str(item["evidence_id"]): item for item in source_records}
    records = [
        _augment_ir_v3(ctx, ir, source_by_id[str(ir["source_evidence_id"])])
        for ir in built.ir_records
    ]
    ids = [str(item["ir_id"]) for item in records]
    cases = [str(item["case"]["case_id"]) for item in records]
    if len(ids) != len(set(ids)) or len(cases) != len(set(cases)):
        raise ValueError("Common IR identity collision detected")

    output_dir = ctx.paths.report_dir / "explanation_ir_v3"
    ir_path = output_dir / "explanation_ir_v3.jsonl"
    summary_path = output_dir / "explanation_ir_v3_summary.csv"
    _write_jsonl(ir_path, records)
    pd.DataFrame(
        [
            {
                "ir_id": item["ir_id"],
                "source_evidence_id": item["source_evidence_id"],
                "dataset_id": item["dataset"]["dataset_id"],
                "experiment_id": item["experiment"]["experiment_id"],
                "case_id": item["case"]["case_id"],
                "source_entity_id": item["case"]["source_entity_id"],
                "case_type": item["case"]["case_type"],
                "predicted_label": item["prediction_summary"]["predicted_label"],
                "probability": item["prediction_summary"]["probability"],
                "feature_factor_count": len(item.get("feature_factors") or []),
                "quality_status": item.get("quality", {}).get("status"),
                "evidence_readiness": item.get("evidence_readiness", {}).get("status"),
            }
            for item in records
        ]
    ).to_csv(summary_path, index=False)
    manifest = {
        "schema_version": "common_explanation_ir_manifest_v3",
        "created_at_utc": _utc_now(),
        **ctx.provenance(),
        "ir_schema_version": "explanation_ir_v3",
        "record_count": len(records),
        "warning_count": len(built.warnings),
        "identity_contract": {
            "primary": "ir_id",
            "dataset_scoped_case_id": "case.case_id",
            "dataset_identity": "dataset.dataset_id",
            "experiment_identity": "experiment.experiment_id",
        },
        "outputs": {"ir_jsonl": str(ir_path), "summary_csv": str(summary_path)},
        "status": "passed",
    }
    manifest_path = ctx.paths.manifest_dir / "common_explanation_ir_manifest_v3.json"
    _write_json(manifest_path, manifest)
    return CommonIRResult(
        manifest_path=manifest_path,
        ir_path=ir_path,
        summary_path=summary_path,
        record_count=len(records),
        warning_count=len(built.warnings),
    )
