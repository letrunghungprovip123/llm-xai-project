from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from research.python.researchops.gates.contracts import GateCheck

from .base import AdapterContext, AdapterResult

_PASS_STATUSES = {
    "PASS",
    "PASSED",
    "PASSED_WITH_WARNINGS",
    "READY",
    "READY_WITH_WARNINGS",
    "READY_WITH_LIMITATIONS",
    "APPROVED",
    "COMPLETED",
    "SUCCESS",
    "RAW_VERIFIED",
    "SCHEMA_AUDIT_PASSED",
    "RELATIONSHIP_AUDIT_PASSED",
    "TARGET_AUDIT_PASSED",
    "MISSING_ANOMALY_AUDIT_PASSED",
    "WARNING_BUT_ACCEPTABLE",
}
_FAIL_STATUSES = {
    "FAIL",
    "FAILED",
    "BLOCKED",
    "REJECTED",
    "ERROR",
    "NOT_READY",
    "FAILED_QUALITY_GATE",
    "FAILED_TRAINING",
    "FAILED_NO_TRAINED_MODELS",
}
_STATUS_KEYS = (
    "status",
    "pipeline_group_status",
    "verdict",
    "result",
    "leakage_status",
)
_FAILURE_WORDS = ("FAIL", "ERROR", "BLOCK", "REJECT", "INVALID")


class AdapterContractError(ValueError):
    """Raised when a report cannot be interpreted without guessing."""


def _read(path: Path) -> Any:
    if not path.is_file():
        raise AdapterContractError(f"Gate report does not exist: {path}")
    if path.suffix.lower() == ".jsonl":
        values: list[Any] = []
        for index, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                values.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise AdapterContractError(
                    f"Invalid JSONL at line {index}: {path}"
                ) from exc
        return values
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AdapterContractError(f"Invalid JSON report: {path}") from exc


def _as_limitations(payload: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("limitations", "warnings"):
        raw = payload.get(key)
        if isinstance(raw, list):
            values.extend(str(item).strip() for item in raw if str(item).strip())
    status = _status_value(payload)
    if status in {"PASSED_WITH_WARNINGS", "READY_WITH_WARNINGS", "READY_WITH_LIMITATIONS"}:
        values.append(status.lower())
    return tuple(dict.fromkeys(values))


def _status_value(payload: dict[str, Any]) -> str | None:
    for key in _STATUS_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    quality = payload.get("quality_report")
    if isinstance(quality, dict):
        value = quality.get("status")
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return None


def _status_passed(status: str) -> bool | None:
    normalized = status.upper()
    if normalized in _PASS_STATUSES:
        return True
    if normalized in _FAIL_STATUSES:
        return False
    if normalized.endswith(("_COMPLETED", "_PASSED", "_VERIFIED", "_READY")):
        return True
    if normalized.startswith(("FAILED", "REJECTED", "BLOCKED")):
        return False
    return None


def _error_count(payload: dict[str, Any]) -> int | None:
    for key in (
        "error_count",
        "failed_check_count",
        "leakage_error_count",
        "training_error_count",
    ):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    errors = payload.get("errors")
    if isinstance(errors, list):
        return len(errors)
    training_errors = payload.get("training_errors")
    if isinstance(training_errors, list):
        return len(training_errors)
    return None


def _row_has_failure(row: dict[str, Any]) -> bool:
    for key in ("passed", "valid", "metric_ready", "contract_pass"):
        if key in row and row[key] is False:
            return True
    for key in ("status", "execution_status", "verdict", "result"):
        value = row.get(key)
        if isinstance(value, str):
            normalized = value.upper()
            state = _status_passed(normalized)
            if state is False or any(word in normalized for word in _FAILURE_WORDS):
                return True
    errors = row.get("errors")
    return isinstance(errors, list) and bool(errors)


def _jsonl_result(payload: list[Any]) -> AdapterResult:
    rows = [item for item in payload if isinstance(item, dict)]
    malformed = len(payload) - len(rows)
    failures = sum(_row_has_failure(row) for row in rows)
    passed = bool(rows) and malformed == 0 and failures == 0
    observed = {
        "record_count": len(payload),
        "object_record_count": len(rows),
        "malformed_record_count": malformed,
        "failure_record_count": failures,
    }
    return AdapterResult(
        outcome="PASSED" if passed else "FAILED",
        expected={
            "minimum_record_count": 1,
            "malformed_record_count": 0,
            "failure_record_count": 0,
        },
        observed=observed,
        checks=(
            GateCheck(
                check_id="records_present",
                passed=bool(rows),
                expected=">=1",
                observed=len(rows),
            ),
            GateCheck(
                check_id="records_well_formed",
                passed=malformed == 0,
                expected=0,
                observed=malformed,
            ),
            GateCheck(
                check_id="records_without_failure",
                passed=failures == 0,
                expected=0,
                observed=failures,
            ),
        ),
    )


def _step_checks(payload: dict[str, Any]) -> tuple[GateCheck, ...]:
    raw = payload.get("step_statuses") or payload.get("new_steps")
    if not isinstance(raw, list) or not raw:
        return ()
    checks: list[GateCheck] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            checks.append(
                GateCheck(
                    check_id=f"step_{index}",
                    passed=False,
                    expected="status object",
                    observed=item,
                )
            )
            continue
        status = str(item.get("status", "")).upper()
        state = _status_passed(status)
        checks.append(
            GateCheck(
                check_id=f"step_{index}",
                passed=state is True,
                expected="accepted status",
                observed=status,
                message=str(item.get("name") or item.get("step") or ""),
            )
        )
    return tuple(checks)


def _quality_gate_checks(payload: dict[str, Any]) -> tuple[GateCheck, ...]:
    raw = payload.get("quality_gates")
    if not isinstance(raw, dict) or not raw:
        return ()
    checks: list[GateCheck] = []
    for name, value in sorted(raw.items()):
        if isinstance(value, bool):
            passed = value
        elif isinstance(value, dict):
            explicit = value.get("passed")
            if isinstance(explicit, bool):
                passed = explicit
            else:
                status = str(value.get("status", "")).upper()
                passed = _status_passed(status) is True
        else:
            # Numeric/string entries often define thresholds rather than results.
            # They are evidence, not independent pass/fail checks.
            continue
        checks.append(
            GateCheck(
                check_id=f"quality_{str(name).lower()}",
                passed=passed,
                expected=True,
                observed=value,
            )
        )
    return tuple(checks)


def _manifest_checks(payload: dict[str, Any]) -> tuple[GateCheck, ...]:
    checks: list[GateCheck] = []
    if isinstance(payload.get("passed"), bool):
        checks.append(
            GateCheck(
                check_id="passed",
                passed=bool(payload["passed"]),
                expected=True,
                observed=payload["passed"],
            )
        )
    status = _status_value(payload)
    if status is not None:
        state = _status_passed(status)
        checks.append(
            GateCheck(
                check_id="status",
                passed=state is True,
                expected="accepted status",
                observed=status,
            )
        )
    errors = _error_count(payload)
    if errors is not None:
        checks.append(
            GateCheck(
                check_id="error_count",
                passed=errors == 0,
                expected=0,
                observed=errors,
            )
        )
    checks.extend(_step_checks(payload))
    checks.extend(_quality_gate_checks(payload))

    if isinstance(payload.get("metric_ready"), bool):
        checks.append(
            GateCheck(
                check_id="metric_ready",
                passed=bool(payload["metric_ready"]),
                expected=True,
                observed=payload["metric_ready"],
            )
        )
    if isinstance(payload.get("completion_score"), (int, float)):
        score = float(payload["completion_score"])
        checks.append(
            GateCheck(
                check_id="completion_score",
                passed=score >= 1.0,
                expected=1.0,
                observed=score,
            )
        )
    if isinstance(payload.get("record_count"), int):
        count = int(payload["record_count"])
        checks.append(
            GateCheck(
                check_id="record_count",
                passed=count > 0,
                expected=">0",
                observed=count,
            )
        )
    if isinstance(payload.get("output_package_count"), int):
        count = int(payload["output_package_count"])
        checks.append(
            GateCheck(
                check_id="output_package_count",
                passed=count > 0,
                expected=">0",
                observed=count,
            )
        )
    if isinstance(payload.get("selected_count"), int):
        count = int(payload["selected_count"])
        checks.append(
            GateCheck(
                check_id="selected_count",
                passed=count > 0,
                expected=">0",
                observed=count,
            )
        )
    split_stats = payload.get("split_stats")
    if isinstance(split_stats, dict):
        split_status = split_stats.get("status")
        if isinstance(split_status, str):
            checks.append(
                GateCheck(
                    check_id="split_status",
                    passed=_status_passed(split_status) is True,
                    expected="accepted status",
                    observed=split_status,
                )
            )
        split_errors = split_stats.get("error_count")
        if isinstance(split_errors, int):
            checks.append(
                GateCheck(
                    check_id="split_error_count",
                    passed=split_errors == 0,
                    expected=0,
                    observed=split_errors,
                )
            )
    return tuple(checks)


def _result_from_checks(
    checks: Iterable[GateCheck],
    *,
    observed: dict[str, Any],
    limitations: tuple[str, ...] = (),
) -> AdapterResult:
    normalized = tuple(checks)
    if not normalized:
        raise AdapterContractError(
            "Report has no supported semantic status; refusing to infer PASS"
        )
    passed = all(item.passed for item in normalized)
    return AdapterResult(
        outcome="PASSED" if passed else "FAILED",
        expected={"all_normalized_checks_pass": True},
        observed=observed,
        checks=normalized,
        limitations=limitations,
    )


class ManifestStatusAdapter:
    adapter_id = "manifest_status_v1"
    adapter_version = 1

    def __init__(self, adapter_id: str | None = None) -> None:
        if adapter_id is not None:
            self.adapter_id = adapter_id

    def evaluate(self, context: AdapterContext) -> AdapterResult:
        payload = _read(context.report_path)
        if isinstance(payload, list):
            return _jsonl_result(payload)
        if not isinstance(payload, dict):
            raise AdapterContractError("Manifest report root must be object or JSONL")
        checks = _manifest_checks(payload)
        return _result_from_checks(
            checks,
            observed={
                "status": _status_value(payload),
                "error_count": _error_count(payload),
                "record_count": payload.get("record_count"),
                "output_package_count": payload.get("output_package_count"),
            },
            limitations=_as_limitations(payload),
        )


class StandardCheckReportAdapter:
    adapter_id = "standard_check_report_v1"
    adapter_version = 1

    def evaluate(self, context: AdapterContext) -> AdapterResult:
        payload = _read(context.report_path)
        if isinstance(payload, list):
            return _jsonl_result(payload)
        if not isinstance(payload, dict):
            raise AdapterContractError("Validation report root must be a JSON object")
        checks = _manifest_checks(payload)
        raw_checks = payload.get("checks")
        if isinstance(raw_checks, dict):
            checks = (*checks, *self._checks_from_mapping(raw_checks))
        return _result_from_checks(
            checks,
            observed={
                "passed": payload.get("passed"),
                "failed_check_count": payload.get("failed_check_count"),
                "status": _status_value(payload),
            },
            limitations=_as_limitations(payload),
        )

    @staticmethod
    def _checks_from_mapping(raw: dict[str, Any]) -> tuple[GateCheck, ...]:
        result: list[GateCheck] = []
        for name, item in sorted(raw.items()):
            if isinstance(item, bool):
                passed = item
                expected: Any = True
                observed: Any = item
            elif isinstance(item, dict):
                explicit = item.get("passed")
                if not isinstance(explicit, bool):
                    continue
                passed = explicit
                expected = item.get("expected")
                observed = item.get("observed")
            else:
                continue
            result.append(
                GateCheck(
                    check_id=f"check_{str(name).lower()}",
                    passed=passed,
                    expected=expected,
                    observed=observed,
                )
            )
        return tuple(result)


class ModelTrainingManifestAdapter(ManifestStatusAdapter):
    adapter_id = "model_training_manifest_v1"

    def evaluate(self, context: AdapterContext) -> AdapterResult:
        payload = _read(context.report_path)
        if not isinstance(payload, dict):
            raise AdapterContractError("Model training manifest must be an object")
        checks = list(_manifest_checks(payload))
        models = payload.get("models_trained")
        model_count = len(models) if isinstance(models, (list, dict)) else 0
        checks.append(
            GateCheck(
                check_id="models_trained",
                passed=model_count > 0,
                expected=">0",
                observed=model_count,
            )
        )
        checks.append(
            GateCheck(
                check_id="best_model",
                passed=bool(payload.get("best_model")),
                expected="non-empty",
                observed=payload.get("best_model"),
            )
        )
        return _result_from_checks(
            checks,
            observed={"status": _status_value(payload), "model_count": model_count},
            limitations=_as_limitations(payload),
        )


class ModelReadyReportAdapter(ManifestStatusAdapter):
    adapter_id = "model_ready_report_v1"


class XAIQualityReportAdapter(ManifestStatusAdapter):
    adapter_id = "xai_quality_report_v1"


class GenerationManifestAdapter(ManifestStatusAdapter):
    adapter_id = "generation_manifest_v1"


class ClaimValidationReleaseAdapter:
    adapter_id = "claim_validation_release_v1"
    adapter_version = 1

    def evaluate(self, context: AdapterContext) -> AdapterResult:
        payload = _read(context.report_path)
        if isinstance(payload, list):
            return _jsonl_result(payload)
        if not isinstance(payload, dict):
            raise AdapterContractError("Claim validation release must be an object")
        gates = payload.get("gates")
        checks: list[GateCheck] = []
        if isinstance(gates, dict):
            for gate_id, item in sorted(gates.items()):
                passed = isinstance(item, dict) and item.get("pass") is True
                checks.append(
                    GateCheck(
                        check_id=str(gate_id).lower(),
                        passed=passed,
                        expected=True,
                        observed=item,
                    )
                )
        if isinstance(payload.get("metric_ready"), bool):
            checks.append(
                GateCheck(
                    check_id="metric_ready",
                    passed=payload["metric_ready"] is True,
                    expected=True,
                    observed=payload["metric_ready"],
                )
            )
        verdict = payload.get("verdict")
        if isinstance(verdict, str):
            checks.append(
                GateCheck(
                    check_id="verdict",
                    passed=verdict.upper() in {"APPROVED", "PASSED", "READY"},
                    expected="APPROVED",
                    observed=verdict,
                )
            )
        return _result_from_checks(
            checks,
            observed={
                "metric_ready": payload.get("metric_ready"),
                "verdict": verdict,
                "completion_score": payload.get("completion_score"),
            },
            limitations=_as_limitations(payload),
        )


class DashboardCertificationAdapter(StandardCheckReportAdapter):
    adapter_id = "dashboard_i18n_certification_v1"

    def evaluate(self, context: AdapterContext) -> AdapterResult:
        payload = _read(context.report_path)
        if not isinstance(payload, dict):
            raise AdapterContractError("Dashboard certification must be an object")
        checks = list(_manifest_checks(payload))
        for group_name in ("pages", "exports"):
            group = payload.get(group_name)
            if isinstance(group, list):
                for index, item in enumerate(group):
                    passed = isinstance(item, dict) and item.get("passed") is True
                    checks.append(
                        GateCheck(
                            check_id=f"{group_name}_{index}",
                            passed=passed,
                            expected=True,
                            observed=item,
                        )
                    )
        catalog = payload.get("catalog")
        if isinstance(catalog, dict) and isinstance(catalog.get("passed"), bool):
            checks.append(
                GateCheck(
                    check_id="catalog",
                    passed=catalog["passed"],
                    expected=True,
                    observed=catalog,
                )
            )
        return _result_from_checks(
            checks,
            observed={"passed": payload.get("passed")},
            limitations=_as_limitations(payload),
        )


class MLflowRegistrationReceiptAdapter:
    adapter_id = "mlflow_registration_receipt_v1"
    adapter_version = 1

    def evaluate(self, context: AdapterContext) -> AdapterResult:
        payload = _read(context.report_path)
        if not isinstance(payload, dict):
            raise AdapterContractError("MLflow receipt must be an object")
        versions = payload.get("versions")
        selected = (
            sum(
                bool(item.get("selected_as_best"))
                for item in versions
                if isinstance(item, dict)
            )
            if isinstance(versions, list)
            else 0
        )
        checks = (
            GateCheck(
                check_id="schema_name",
                passed=payload.get("schema_name") == "mlflow_registration_receipt_v1",
                expected="mlflow_registration_receipt_v1",
                observed=payload.get("schema_name"),
            ),
            GateCheck(
                check_id="candidate_version",
                passed=bool(str(payload.get("candidate_version", "")).strip()),
                expected="non-empty",
                observed=payload.get("candidate_version"),
            ),
            GateCheck(
                check_id="versions_registered",
                passed=isinstance(versions, list) and len(versions) > 0,
                expected=">0",
                observed=len(versions) if isinstance(versions, list) else 0,
            ),
            GateCheck(
                check_id="single_best_model",
                passed=selected == 1,
                expected=1,
                observed=selected,
            ),
            GateCheck(
                check_id="source_model_artifact",
                passed=bool(payload.get("source_model_artifact_id")),
                expected="non-empty",
                observed=payload.get("source_model_artifact_id"),
            ),
        )
        return _result_from_checks(
            checks,
            observed={
                "registered_model_name": payload.get("registered_model_name"),
                "candidate_version": payload.get("candidate_version"),
                "version_count": len(versions) if isinstance(versions, list) else 0,
            },
        )
