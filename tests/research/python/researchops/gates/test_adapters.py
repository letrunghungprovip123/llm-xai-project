from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.python.researchops.gates.adapters import AdapterContext, GateAdapterRegistry
from research.python.researchops.gates.adapters.builtin import AdapterContractError


def _context(path: Path, *, gate_id: str = "MODEL_READY") -> AdapterContext:
    return AdapterContext(
        gate_id=gate_id,
        report_path=path,
        artifact_id="artifact_model_ready_report_01J00000000000000000000000",
        artifact_type="model_ready_report",
        manifest_sha256="a" * 64,
    )


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_manifest_adapter_accepts_explicit_pass_and_rejects_blocked(
    tmp_path: Path,
) -> None:
    adapter = GateAdapterRegistry().get("manifest_status_v1", 1)
    passed = adapter.evaluate(
        _context(_write(tmp_path / "pass.json", {"status": "PASSED", "errors": []}))
    )
    failed = adapter.evaluate(
        _context(_write(tmp_path / "fail.json", {"status": "BLOCKED", "errors": ["x"]}))
    )
    assert passed.outcome == "PASSED"
    assert failed.outcome == "FAILED"


def test_manifest_adapter_fails_closed_when_report_has_no_supported_signal(
    tmp_path: Path,
) -> None:
    adapter = GateAdapterRegistry().get("manifest_status_v1", 1)
    with pytest.raises(AdapterContractError, match="refusing to infer PASS"):
        adapter.evaluate(_context(_write(tmp_path / "unknown.json", {"foo": "bar"})))


def test_jsonl_adapter_requires_records_and_rejects_error_rows(tmp_path: Path) -> None:
    adapter = GateAdapterRegistry().get("manifest_status_v1", 1)
    path = tmp_path / "rows.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"id": 1, "execution_status": "COMPLETED"}),
                json.dumps({"id": 2, "execution_status": "ERROR"}),
            ]
        ),
        encoding="utf-8",
    )
    result = adapter.evaluate(_context(path))
    assert result.outcome == "FAILED"
    assert result.observed["failure_record_count"] == 1


def test_model_training_adapter_requires_a_best_model_and_trained_models(
    tmp_path: Path,
) -> None:
    adapter = GateAdapterRegistry().get("model_training_manifest_v1", 1)
    passed = adapter.evaluate(
        _context(
            _write(
                tmp_path / "training.json",
                {
                    "status": "passed",
                    "training_errors": [],
                    "models_trained": [{"model": "hist_gradient_boosting"}],
                    "best_model": "hist_gradient_boosting",
                },
            )
        )
    )
    failed = adapter.evaluate(
        _context(
            _write(
                tmp_path / "training-failed.json",
                {
                    "status": "passed",
                    "training_errors": [],
                    "models_trained": [],
                    "best_model": None,
                },
            )
        )
    )
    assert passed.outcome == "PASSED"
    assert failed.outcome == "FAILED"


def test_claim_release_adapter_normalizes_c1_c7_without_guessing(
    tmp_path: Path,
) -> None:
    adapter = GateAdapterRegistry().get("claim_validation_release_v1", 1)
    payload = {
        "metric_ready": True,
        "verdict": "APPROVED",
        "gates": {
            f"C{index}": {"pass": True, "evidence": "ok"}
            for index in range(1, 8)
        },
    }
    result = adapter.evaluate(_context(_write(tmp_path / "release.json", payload)))
    assert result.outcome == "PASSED"
    assert {item.check_id for item in result.checks} >= {
        "c1",
        "c2",
        "c3",
        "c4",
        "c5",
        "c6",
        "c7",
    }


def test_registry_contains_every_adapter_declared_by_stage_registry() -> None:
    from research.python.researchops.stage_registry.loader import load_stage_registry

    registry = GateAdapterRegistry()
    declared = {
        (stage.verification.adapter_id, stage.verification.adapter_version)
        for stage in load_stage_registry().stages
    }
    assert declared <= registry.identities()
