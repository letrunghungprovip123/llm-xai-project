from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ml.scripts.explanation_ir_layer.config import (
    DEFAULT_XAI_CONCEPT_AGGREGATION_PATH,
    DEFAULT_XAI_QUALITY_MANIFEST_PATH,
    DEFAULT_XAI_QUALITY_SUMMARY_PATH,
    RUN_MODE_AUTO,
    RUN_MODE_EVALUATION,
    RUN_MODE_INFERENCE,
    mode_has_ground_truth,
    resolve_optional_input_path,
    resolve_xai_evidence_input_path,
    validate_run_mode,
)


@dataclass
class ExplanationIRInputs:
    run_mode: str
    has_ground_truth: bool
    xai_evidence_path: Path
    evidence_records: List[Dict[str, Any]]
    xai_quality_summary_path: Optional[Path]
    xai_concept_aggregation_path: Optional[Path]
    xai_quality_manifest_path: Optional[Path]
    quality_by_evidence_id: Dict[str, Dict[str, Any]]
    concepts_by_evidence_id: Dict[str, List[Dict[str, Any]]]
    quality_manifest: Dict[str, Any]
    warnings: List[str]


def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    p = Path(path)
    records: List[Dict[str, Any]] = []

    with p.open("r", encoding="utf-8") as f:
        line_number = 0

        for line in f:
            line_number += 1
            text = line.strip()

            if not text:
                continue

            try:
                obj = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {p}:{line_number}: {exc}") from exc

            if not isinstance(obj, dict):
                raise ValueError(f"Record at {p}:{line_number} is not a JSON object.")

            records.append(obj)

    if not records:
        raise ValueError(f"No records found in {p}")

    return records


def read_json_dict(path: Optional[str | Path]) -> Dict[str, Any]:
    if path is None:
        return {}

    p = Path(path)

    if not p.exists():
        return {}

    with p.open("r", encoding="utf-8") as f:
        obj = json.load(f)

    if isinstance(obj, dict):
        return obj

    return {}


def read_csv_rows(path: Optional[str | Path]) -> List[Dict[str, Any]]:
    if path is None:
        return []

    p = Path(path)

    if not p.exists():
        return []

    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def get_nested_value(data: Dict[str, Any], path: str) -> Any:
    cur: Any = data

    for part in path.split("."):
        if not isinstance(cur, dict):
            return None

        if part not in cur:
            return None

        cur = cur[part]

    return cur


def detect_mode(records: List[Dict[str, Any]]) -> str:
    modes = set()

    for record in records:
        value = record.get("run_mode") or get_nested_value(record, "metadata.run_mode")

        if isinstance(value, str):
            mode = value.strip().lower()
            if mode in (RUN_MODE_EVALUATION, RUN_MODE_INFERENCE):
                modes.add(mode)

    if not modes:
        raise ValueError("Could not infer run_mode from XAI evidence. Use --mode explicitly.")

    if len(modes) > 1:
        raise ValueError(f"Mixed run modes found in evidence file: {sorted(modes)}")

    return next(iter(modes))


def load_quality_summary(path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    rows = read_csv_rows(path)
    result: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        evidence_id = row.get("evidence_id")

        if evidence_id is None:
            continue

        evidence_id = str(evidence_id).strip()

        if evidence_id:
            result[evidence_id] = row

    return result


def load_concept_aggregation(path: Optional[Path]) -> Dict[str, List[Dict[str, Any]]]:
    rows = read_csv_rows(path)
    result: Dict[str, List[Dict[str, Any]]] = {}

    for row in rows:
        evidence_id = row.get("evidence_id")

        if evidence_id is None:
            continue

        evidence_id = str(evidence_id).strip()

        if not evidence_id:
            continue

        result.setdefault(evidence_id, []).append(row)

    for evidence_id in result:
        result[evidence_id].sort(
            key=lambda item: int(float(item.get("concept_rank") or 999999))
            if str(item.get("concept_rank") or "").strip()
            else 999999
        )

    return result


def load_xai_evidence_inputs(
    run_mode: str,
    input_path: Optional[str | Path] = None,
    xai_quality_summary_path: Optional[str | Path] = None,
    xai_concept_aggregation_path: Optional[str | Path] = None,
    xai_quality_manifest_path: Optional[str | Path] = None,
) -> ExplanationIRInputs:
    requested_mode = validate_run_mode(run_mode)
    evidence_path = resolve_xai_evidence_input_path(requested_mode, input_path)
    evidence_records = read_jsonl(evidence_path)

    if requested_mode == RUN_MODE_AUTO:
        resolved_mode = detect_mode(evidence_records)
    else:
        resolved_mode = requested_mode

    has_ground_truth = mode_has_ground_truth(resolved_mode)

    quality_summary = resolve_optional_input_path(
        xai_quality_summary_path,
        DEFAULT_XAI_QUALITY_SUMMARY_PATH,
    )
    concept_aggregation = resolve_optional_input_path(
        xai_concept_aggregation_path,
        DEFAULT_XAI_CONCEPT_AGGREGATION_PATH,
    )
    quality_manifest = resolve_optional_input_path(
        xai_quality_manifest_path,
        DEFAULT_XAI_QUALITY_MANIFEST_PATH,
    )

    warnings: List[str] = []

    if quality_summary is None:
        warnings.append("Batch G+ quality summary file was not found.")

    if concept_aggregation is None:
        warnings.append("Batch G+ concept aggregation file was not found.")

    if quality_manifest is None:
        warnings.append("Batch G+ quality manifest file was not found.")

    for idx, record in enumerate(evidence_records):
        for key in ["model", "customer", "prediction", "shap", "local_features"]:
            if key not in record:
                warnings.append(f"record_index={idx}: missing {key}")

        if not (record.get("evidence_id") or record.get("source_evidence_id")):
            warnings.append(f"record_index={idx}: missing evidence_id")

        local_features = record.get("local_features")
        if local_features is not None and not isinstance(local_features, list):
            warnings.append(f"record_index={idx}: local_features is not a list")

    return ExplanationIRInputs(
        run_mode=resolved_mode,
        has_ground_truth=has_ground_truth,
        xai_evidence_path=evidence_path,
        evidence_records=evidence_records,
        xai_quality_summary_path=quality_summary,
        xai_concept_aggregation_path=concept_aggregation,
        xai_quality_manifest_path=quality_manifest,
        quality_by_evidence_id=load_quality_summary(quality_summary),
        concepts_by_evidence_id=load_concept_aggregation(concept_aggregation),
        quality_manifest=read_json_dict(quality_manifest),
        warnings=warnings,
    )


def summarize_loaded_inputs(inputs: ExplanationIRInputs) -> Dict[str, Any]:
    return {
        "run_mode": inputs.run_mode,
        "has_ground_truth": inputs.has_ground_truth,
        "xai_evidence_path": str(inputs.xai_evidence_path),
        "evidence_record_count": len(inputs.evidence_records),
        "xai_quality_summary_path": str(inputs.xai_quality_summary_path)
        if inputs.xai_quality_summary_path
        else None,
        "xai_concept_aggregation_path": str(inputs.xai_concept_aggregation_path)
        if inputs.xai_concept_aggregation_path
        else None,
        "xai_quality_manifest_path": str(inputs.xai_quality_manifest_path)
        if inputs.xai_quality_manifest_path
        else None,
        "quality_metric_record_count": len(inputs.quality_by_evidence_id),
        "concept_metric_record_count": len(inputs.concepts_by_evidence_id),
        "warning_count": len(inputs.warnings),
    }