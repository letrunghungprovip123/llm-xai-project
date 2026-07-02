"""
Loaders for Batch I - LLM Explanation Layer.

This module loads Batch H Explanation IR records.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ml.scripts.llm_explanation_layer.config import (
    DEFAULT_IR_INPUT_INFERENCE_PATH,
    DEFAULT_IR_INPUT_PATH,
    RUN_MODE_AUTO,
    RUN_MODE_EVALUATION,
    RUN_MODE_INFERENCE,
)


@dataclass(frozen=True)
class LLMExplanationInputs:
    ir_records: List[Dict[str, Any]]
    input_path: Path
    run_mode: str
    has_ground_truth: bool
    warnings: List[str]
    errors: List[str]


def load_jsonl_records(path: str | Path) -> List[Dict[str, Any]]:
    """Load JSONL records from disk."""
    path = Path(path)

    records: List[Dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            text = line.strip()

            if not text:
                continue

            try:
                record = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON at line {line_number} in {path}: {exc}"
                ) from exc

            if not isinstance(record, dict):
                raise ValueError(
                    f"Line {line_number} in {path} is not a JSON object."
                )

            records.append(record)

    return records


def get_nested_value(
    data: Dict[str, Any],
    path: str,
    default: Any = None,
) -> Any:
    """Safely read nested dictionary values with dot notation."""
    current: Any = data

    for part in path.split("."):
        if not isinstance(current, dict):
            return default

        if part not in current:
            return default

        current = current[part]

    return current


def infer_record_run_mode(record: Dict[str, Any]) -> Optional[str]:
    """Infer run_mode from one IR record."""
    value = record.get("run_mode")

    if value is None:
        value = get_nested_value(record, "metadata.run_mode")

    if value is None:
        return None

    return str(value).strip().lower()


def infer_record_has_ground_truth(record: Dict[str, Any]) -> Optional[bool]:
    """Infer has_ground_truth from one IR record."""
    value = record.get("has_ground_truth")

    if isinstance(value, bool):
        return value

    value = get_nested_value(record, "prediction_summary.has_ground_truth")

    if isinstance(value, bool):
        return value

    return None


def detect_mode_from_records(records: List[Dict[str, Any]]) -> str:
    """Detect run mode from loaded records."""
    modes = {
        infer_record_run_mode(record)
        for record in records
        if infer_record_run_mode(record) is not None
    }

    if not modes:
        return RUN_MODE_EVALUATION

    if len(modes) > 1:
        raise ValueError(f"Mixed run modes found in IR records: {sorted(modes)}")

    return next(iter(modes))


def detect_has_ground_truth_from_records(records: List[Dict[str, Any]]) -> bool:
    """Detect has_ground_truth from loaded records."""
    values = [
        infer_record_has_ground_truth(record)
        for record in records
        if infer_record_has_ground_truth(record) is not None
    ]

    if not values:
        return False

    return bool(values[0])


def validate_minimal_ir_record(
    record: Dict[str, Any],
    index: int,
) -> tuple[List[str], List[str]]:
    """
    Validate minimal fields required by Batch I.

    Returns:
        (warnings, errors)
    """
    warnings: List[str] = []
    errors: List[str] = []

    if not record.get("ir_id"):
        errors.append(f"record_index={index}: missing ir_id.")

    if not record.get("source_evidence_id"):
        errors.append(f"record_index={index}: missing source_evidence_id.")

    if not record.get("trace_id"):
        errors.append(f"record_index={index}: missing trace_id.")

    if not isinstance(record.get("llm_input_contract"), dict):
        errors.append(f"record_index={index}: missing llm_input_contract.")

    contract = record.get("llm_input_contract") or {}

    if not isinstance(contract.get("prediction"), dict):
        errors.append(
            f"record_index={index}: llm_input_contract.prediction is missing."
        )

    if not isinstance(contract.get("allowed_claim_ids"), list):
        errors.append(
            f"record_index={index}: llm_input_contract.allowed_claim_ids is missing."
        )

    if not isinstance(contract.get("forbidden_rule_ids"), list):
        errors.append(
            f"record_index={index}: llm_input_contract.forbidden_rule_ids is missing."
        )

    if not isinstance(contract.get("main_concepts"), list):
        warnings.append(
            f"record_index={index}: llm_input_contract.main_concepts is missing or not a list."
        )

    if not isinstance(contract.get("main_risk_increasing_factors"), list):
        warnings.append(
            f"record_index={index}: llm_input_contract.main_risk_increasing_factors is missing or not a list."
        )

    if not isinstance(contract.get("main_risk_decreasing_factors"), list):
        warnings.append(
            f"record_index={index}: llm_input_contract.main_risk_decreasing_factors is missing or not a list."
        )

    return warnings, errors


def resolve_default_input_path(run_mode: str) -> Path:
    """Resolve default IR input path by mode."""
    if run_mode == RUN_MODE_INFERENCE:
        return DEFAULT_IR_INPUT_INFERENCE_PATH

    return DEFAULT_IR_INPUT_PATH


def load_llm_explanation_inputs(
    run_mode: str,
    input_path: str | Path | None = None,
) -> LLMExplanationInputs:
    """
    Load Batch H Explanation IR records for Batch I.
    """
    requested_mode = str(run_mode).strip().lower()

    if input_path is None:
        if requested_mode == RUN_MODE_AUTO:
            path = DEFAULT_IR_INPUT_PATH
        else:
            path = resolve_default_input_path(requested_mode)
    else:
        path = Path(input_path)

    if not path.exists():
        raise FileNotFoundError(f"IR input file not found: {path}")

    records = load_jsonl_records(path)

    if not records:
        raise ValueError(f"No IR records found in input file: {path}")

    detected_mode = detect_mode_from_records(records)
    detected_has_ground_truth = detect_has_ground_truth_from_records(records)

    final_mode = detected_mode if requested_mode == RUN_MODE_AUTO else requested_mode

    warnings: List[str] = []
    errors: List[str] = []

    if requested_mode != RUN_MODE_AUTO and detected_mode != final_mode:
        warnings.append(
            f"Requested run_mode={final_mode!r}, but IR records appear to be "
            f"run_mode={detected_mode!r}."
        )

    for idx, record in enumerate(records):
        record_warnings, record_errors = validate_minimal_ir_record(record, idx)
        warnings.extend(record_warnings)
        errors.extend(record_errors)

    return LLMExplanationInputs(
        ir_records=records,
        input_path=path,
        run_mode=final_mode,
        has_ground_truth=detected_has_ground_truth,
        warnings=warnings,
        errors=errors,
    )