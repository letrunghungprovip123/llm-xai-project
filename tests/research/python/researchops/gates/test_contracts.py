from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from research.python.researchops.gates.contracts import (
    GateAdapterIdentity,
    GateCheck,
    GateEvaluationDraft,
    GatePolicyIdentity,
    GateScope,
    GateSource,
)


def _draft(**updates) -> GateEvaluationDraft:
    payload = dict(
        gate_id="MODEL_READY",
        scope=GateScope(type="artifact", id="artifact_model_ready_report_test"),
        outcome="PASSED",
        adapter=GateAdapterIdentity(id="model_ready_report_v1", version=1),
        policy=GatePolicyIdentity(id="scientific_quality", version="1"),
        source=GateSource(
            artifact_id="artifact_model_ready_report_test",
            manifest_sha256="a" * 64,
            contract="model_ready_report",
        ),
        checks=(GateCheck(check_id="status", passed=True),),
        evaluated_at=datetime.now(timezone.utc),
    )
    payload.update(updates)
    return GateEvaluationDraft(**payload)


def test_gate_contract_is_strict_and_outcome_matches_checks() -> None:
    draft = _draft()
    assert draft.schema_version == "gate_evaluation_v1"
    with pytest.raises(ValidationError):
        _draft(outcome="FAILED")
    with pytest.raises(ValidationError):
        GateEvaluationDraft(**{**draft.model_dump(), "unexpected": True})


def test_source_artifact_identity_is_all_or_nothing() -> None:
    with pytest.raises(ValidationError):
        GateSource(
            artifact_id="artifact_x",
            contract="model_ready_report",
        )
