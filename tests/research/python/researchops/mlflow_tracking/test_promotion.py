from datetime import datetime, timezone

import pytest

from research.python.researchops.mlflow_tracking.contracts import load_registry_policy
from research.python.researchops.mlflow_tracking.exceptions import MLflowIntegrityError
from research.python.researchops.mlflow_tracking.promotion import promote_candidate
from research.python.researchops.mlflow_tracking.registry_gateway import ModelVersionSnapshot
from research.python.researchops.ops_core.db.models import Approval, GateResult
from tests.research.python.researchops.mlflow_tracking.test_registry import FakeRegistryGateway
from tests.research.python.researchops.ops_core.fakes import FakeRepository


def _gateway():
    gateway = FakeRegistryGateway()
    gateway.versions.append(ModelVersionSnapshot(
        "credit-risk-predictor", "3", "run-3", "runs:/run-3/model", "READY",
        {"researchops.source_manifest_verified": "PASSED"},
    ))
    gateway.set_alias("credit-risk-predictor", "candidate", "3")
    return gateway


def test_promotion_requires_approval_and_all_blocking_gates():
    repository = FakeRepository()
    gateway = _gateway()
    with pytest.raises(MLflowIntegrityError):
        promote_candidate(
            version="3", approval_id="approval-1", actor="reviewer", request_id=None,
            gateway=gateway, repository=repository, policy=load_registry_policy(),
        )

    repository.approval_items.append(Approval(
        id="approval-1", target_type="model_version", target_id="credit-risk-predictor:3",
        policy="MODEL_PROMOTION", status="APPROVED", requested_by="owner",
        decided_by="reviewer", decided_at=datetime.now(timezone.utc),
    ))
    for gate_id in ("MODEL_READY", "XAI_QUALITY_READY", "MLFLOW_MODEL_REGISTERED"):
        repository.gates.append(GateResult(
            id=f"gate-{gate_id}", gate_id=gate_id, scope_type="model_version",
            scope_id="credit-risk-predictor:3", status="PASSED", evaluation_outcome="PASSED", effective_status="PASSED", current_evaluation_id=f"eval-{gate_id}", blocking=True,
            severity="ERROR", expected={}, observed={}, details={}, source_contracts=[],
        ))
    result = promote_candidate(
        version="3", approval_id="approval-1", actor="reviewer", request_id="request-1",
        gateway=gateway, repository=repository, policy=load_registry_policy(),
    )
    assert result.champion_version == "3"
    assert gateway.alias_version("credit-risk-predictor", "champion") == "3"
    assert repository.audits[-1].action == "mlflow.champion_promoted"
