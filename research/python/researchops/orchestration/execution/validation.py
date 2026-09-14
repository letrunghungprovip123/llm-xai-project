from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from research.python.researchops.contracts.io import project_root

from .contracts import PipelineExecutionReceipt, StageExecutionResult


_SCHEMAS = {
    "stage_execution_result_v1": (
        StageExecutionResult,
        "config/platform/schemas/stage_execution_result_v1.schema.json",
    ),
    "pipeline_execution_receipt_v1": (
        PipelineExecutionReceipt,
        "config/platform/schemas/pipeline_execution_receipt_v1.schema.json",
    ),
}


def validate_execution_contracts(root: Path | None = None) -> dict[str, Any]:
    resolved = (root or project_root()).resolve()
    checked: list[dict[str, str]] = []
    errors: list[str] = []
    for contract_id, (model, relative_path) in _SCHEMAS.items():
        path = resolved / relative_path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(payload)
            generated = model.model_json_schema()
            required = set(generated.get("required", []))
            observed = set(payload.get("required", []))
            if required != observed:
                errors.append(
                    f"{contract_id}: required-field drift "
                    f"generated={sorted(required)} observed={sorted(observed)}"
                )
            checked.append({"contract_id": contract_id, "path": relative_path})
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"{contract_id}: {exc}")
    return {
        "schema_version": "execution_contract_validation_v1",
        "passed": not errors,
        "checked": checked,
        "errors": errors,
    }
