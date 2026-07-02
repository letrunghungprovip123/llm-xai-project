"""
Loaders for Batch H - Concept-aware Explanation IR Layer.

This module loads structured XAI evidence records produced by Batch G.

Main input:
    data/reports/xai/xai_local_evidence.jsonl

Important:
- This module does NOT read raw data.
- This module does NOT load model artifacts.
- This module does NOT compute SHAP.
- This module only loads and lightly validates structured XAI evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ml.scripts.explanation_ir_layer.config import (
    RUN_MODE_AUTO,
    RUN_MODE_EVALUATION,
    RUN_MODE_INFERENCE,
    validate_run_mode,
    validate_resolved_mode,
    resolve_xai_evidence_input_path,
    validate_input_path_exists,
    mode_has_ground_truth,
)


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass(frozen=True)
class ExplanationIRInputs:
    """
    Loaded inputs for Batch H.

    Attributes:
        run_mode:
            Resolved mode: evaluation or inference.
            This should never be "auto" after loading.

        has_ground_truth:
            Whether this input is expected to contain ground truth labels.

        input_path:
            Resolved path to xai_local_evidence.jsonl.

        evidence_records:
            List of dictionaries loaded from JSONL.

        record_count:
            Number of loaded evidence records.

        warnings:
            Non-fatal issues found while loading.
    """

    run_mode: str
    has_ground_truth: bool
    input_path: Path
    evidence_records: List[Dict[str, Any]]
    record_count: int
    warnings: List[str]


# =============================================================================
# JSONL loading
# =============================================================================

def load_jsonl_records(path: str | Path) -> List[Dict[str, Any]]:
    """
    Load a JSONL file into a list of dictionaries.

    Raises:
        FileNotFoundError:
            if the file does not exist

        ValueError:
            if any non-empty line is not valid JSON or not a JSON object
    """
    resolved_path = validate_input_path_exists(path)
    records: List[Dict[str, Any]] = []

    with resolved_path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            stripped = line.strip()

            if not stripped:
                continue

            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON at {resolved_path}:{line_number}. "
                    f"Original error: {exc}"
                ) from exc

            if not isinstance(obj, dict):
                raise ValueError(
                    f"Invalid JSONL record at {resolved_path}:{line_number}. "
                    f"Expected a JSON object, got {type(obj).__name__}."
                )

            records.append(obj)

    if not records:
        raise ValueError(f"No evidence records found in input file: {resolved_path}")

    return records


# =============================================================================
# Evidence schema helpers
# =============================================================================

def get_nested_value(
    data: Dict[str, Any],
    path: str,
    default: Any = None,
) -> Any:
    """
    Safely get a nested value from a dictionary using dot notation.

    Example:
        get_nested_value(record, "prediction.y_true")
    """
    current: Any = data

    for part in path.split("."):
        if not isinstance(current, dict):
            return default

        if part not in current:
            return default

        current = current[part]

    return current


def infer_record_run_mode(record: Dict[str, Any]) -> Optional[str]:
    """
    Infer run mode from a single evidence record.

    Batch G should store run_mode either at top level or inside metadata.
    This helper checks both locations.
    """
    candidates = [
        record.get("run_mode"),
        get_nested_value(record, "metadata.run_mode"),
    ]

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            mode = candidate.strip().lower()
            if mode in (RUN_MODE_EVALUATION, RUN_MODE_INFERENCE):
                return mode

    return None


def infer_record_has_ground_truth(record: Dict[str, Any]) -> Optional[bool]:
    """
    Infer has_ground_truth from a single evidence record.

    Batch G should store has_ground_truth either at top level or inside metadata.
    If missing, infer from prediction.y_true when possible.
    """
    candidates = [
        record.get("has_ground_truth"),
        get_nested_value(record, "metadata.has_ground_truth"),
    ]

    for candidate in candidates:
        if isinstance(candidate, bool):
            return candidate

    y_true = get_nested_value(record, "prediction.y_true")

    if y_true is None:
        return None

    return True


def validate_minimal_evidence_record(
    record: Dict[str, Any],
    record_index: int,
) -> List[str]:
    """
    Validate minimal fields needed by Batch H.

    This function returns warnings instead of raising for most missing fields.
    The builder will later decide whether a record can be converted into IR.
    """
    warnings: List[str] = []

    required_top_level = [
        "model",
        "customer",
        "prediction",
        "shap",
    ]

    for key in required_top_level:
        if key not in record:
            warnings.append(
                f"record_index={record_index}: missing top-level field '{key}'."
            )

    evidence_id = record.get("evidence_id") or record.get("source_evidence_id")
    if not evidence_id:
        warnings.append(
            f"record_index={record_index}: missing evidence_id/source_evidence_id."
        )

    local_features = record.get("local_features")
    if local_features is None:
        warnings.append(
            f"record_index={record_index}: missing local_features."
        )
    elif not isinstance(local_features, list):
        warnings.append(
            f"record_index={record_index}: local_features must be a list."
        )
    elif len(local_features) == 0:
        warnings.append(
            f"record_index={record_index}: local_features is empty."
        )

    return warnings


# =============================================================================
# Mode resolution
# =============================================================================

def detect_mode_from_records(records: List[Dict[str, Any]]) -> str:
    """
    Detect run mode from loaded evidence records.

    Rules:
        - All records with detectable mode must agree.
        - If no record has mode, raise ValueError.
        - Mixed evaluation/inference in one JSONL is not allowed in v1.
    """
    detected_modes = set()

    for record in records:
        mode = infer_record_run_mode(record)
        if mode is not None:
            detected_modes.add(mode)

    if not detected_modes:
        raise ValueError(
            "Could not infer run_mode from evidence records. "
            "Use --mode evaluation or --mode inference, or ensure Batch G "
            "writes run_mode into evidence records."
        )

    if len(detected_modes) > 1:
        raise ValueError(
            f"Mixed run modes found in one evidence file: {sorted(detected_modes)}. "
            "Batch H v1 expects one mode per input file."
        )

    return next(iter(detected_modes))


def validate_records_match_mode(
    records: List[Dict[str, Any]],
    run_mode: str,
) -> List[str]:
    """
    Validate that records are compatible with the resolved run mode.

    Returns warnings. Severe problems are still warnings here because the builder
    can later mark individual records as failed.
    """
    mode = validate_resolved_mode(run_mode)
    expected_has_ground_truth = mode_has_ground_truth(mode)

    warnings: List[str] = []

    for idx, record in enumerate(records):
        record_mode = infer_record_run_mode(record)
        if record_mode is not None and record_mode != mode:
            warnings.append(
                f"record_index={idx}: record run_mode={record_mode!r} "
                f"does not match resolved run_mode={mode!r}."
            )

        record_has_ground_truth = infer_record_has_ground_truth(record)

        if record_has_ground_truth is not None:
            if record_has_ground_truth != expected_has_ground_truth:
                warnings.append(
                    f"record_index={idx}: has_ground_truth={record_has_ground_truth} "
                    f"does not match expected value {expected_has_ground_truth} "
                    f"for run_mode={mode!r}."
                )

        y_true = get_nested_value(record, "prediction.y_true")

        if mode == RUN_MODE_EVALUATION and y_true is None:
            warnings.append(
                f"record_index={idx}: evaluation mode expects prediction.y_true, "
                "but it is missing/null."
            )

        if mode == RUN_MODE_INFERENCE and y_true is not None:
            warnings.append(
                f"record_index={idx}: inference mode should not have prediction.y_true, "
                f"but got {y_true!r}."
            )

    return warnings


# =============================================================================
# Public loader
# =============================================================================

def load_xai_evidence_inputs(
    run_mode: Optional[str] = None,
    input_path: Optional[str | Path] = None,
) -> ExplanationIRInputs:
    """
    Load all inputs needed by Batch H.

    Args:
        run_mode:
            evaluation, inference, or auto.
            If None, config.DEFAULT_RUN_MODE is used.

        input_path:
            Optional override path to xai_local_evidence.jsonl.

    Returns:
        ExplanationIRInputs with resolved run_mode.
    """
    requested_mode = validate_run_mode(run_mode)
    resolved_input_path = resolve_xai_evidence_input_path(
        requested_mode,
        input_path=input_path,
    )

    records = load_jsonl_records(resolved_input_path)

    if requested_mode == RUN_MODE_AUTO:
        resolved_mode = detect_mode_from_records(records)
    else:
        resolved_mode = requested_mode

    validate_resolved_mode(resolved_mode)

    warnings: List[str] = []

    for idx, record in enumerate(records):
        warnings.extend(validate_minimal_evidence_record(record, idx))

    warnings.extend(validate_records_match_mode(records, resolved_mode))

    return ExplanationIRInputs(
        run_mode=resolved_mode,
        has_ground_truth=mode_has_ground_truth(resolved_mode),
        input_path=resolved_input_path,
        evidence_records=records,
        record_count=len(records),
        warnings=warnings,
    )


def summarize_loaded_inputs(inputs: ExplanationIRInputs) -> Dict[str, Any]:
    """
    Return a JSON-serializable summary of loaded inputs.
    """
    return {
        "run_mode": inputs.run_mode,
        "has_ground_truth": inputs.has_ground_truth,
        "input_path": str(inputs.input_path),
        "record_count": inputs.record_count,
        "warning_count": len(inputs.warnings),
        "warnings": inputs.warnings,
    }


if __name__ == "__main__":
    import json

    loaded = load_xai_evidence_inputs()
    print(json.dumps(summarize_loaded_inputs(loaded), indent=2, ensure_ascii=False))