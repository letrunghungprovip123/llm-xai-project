from __future__ import annotations

from dataclasses import dataclass

from research.python.researchops.ops_core.repositories.protocols import OpsRepository
from research.python.researchops.promotion import (
    ModelPromotionService,
    PromotionDecisionError,
    promotion_request_key,
)

from .contracts import RegistryPolicy
from .exceptions import MLflowIntegrityError
from .registry_gateway import RegistryGateway


@dataclass(frozen=True)
class PromotionResult:
    registered_model_name: str
    version: str
    approval_id: str
    previous_champion_version: str | None
    champion_version: str


def promote_candidate(
    *,
    version: str,
    approval_id: str,
    actor: str,
    request_id: str | None,
    gateway: RegistryGateway,
    repository: OpsRepository,
    policy: RegistryPolicy,
) -> PromotionResult:
    name = policy.registered_model_name
    key = promotion_request_key(
        {
            "target_type": "model_version",
            "target_id": f"{name}:{version}",
            "approval_id": approval_id,
            "reason": "Promote governed candidate to champion",
        }
    )
    try:
        decision = ModelPromotionService(repository, gateway).promote(
            model_name=name,
            version=version,
            approval_id=approval_id,
            actor=actor,
            reason="Promote governed candidate to champion",
            idempotency_key=key,
            request_id=request_id,
        )
    except PromotionDecisionError as exc:
        raise MLflowIntegrityError(str(exc)) from exc
    previous = decision.previous_external_state.get("champion_version")
    return PromotionResult(name, version, approval_id, previous, version)
