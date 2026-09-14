from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from research.python.researchops.contracts.io import project_root


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApprovalRequirement(StrictModel):
    required: bool = True
    policy: str = Field(min_length=1)
    separation_of_duties: bool = True


class PromotionSideEffects(StrictModel):
    mlflow_candidate_alias: str | None = None
    mlflow_champion_alias: str | None = None
    mlflow_archive_alias: str | None = None

    @model_validator(mode="after")
    def aliases_are_complete(self) -> "PromotionSideEffects":
        values = (
            self.mlflow_candidate_alias,
            self.mlflow_champion_alias,
            self.mlflow_archive_alias,
        )
        if any(item is not None for item in values) and not all(
            item is not None for item in values
        ):
            raise ValueError("MLflow alias side effects must declare all aliases")
        return self


class PromotionPolicy(StrictModel):
    policy_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    version: int = Field(ge=1)
    target_type: Literal["model_version", "release"]
    target_kinds: tuple[str, ...] = Field(min_length=1)
    from_states: tuple[str, ...] = Field(min_length=1)
    to_state: str = Field(min_length=1)
    required_gates: tuple[str, ...] = Field(min_length=1)
    non_waivable_gates: tuple[str, ...] = ()
    waiver_mode: Literal["FORBIDDEN", "READY_WITH_LIMITATIONS"] = "FORBIDDEN"
    waived_to_state: str | None = None
    waiver_approval_policy: str = "WAIVER"
    approval: ApprovalRequirement
    side_effects: PromotionSideEffects = PromotionSideEffects()

    @model_validator(mode="after")
    def safe_policy(self) -> "PromotionPolicy":
        for name, values in {
            "target_kinds": self.target_kinds,
            "from_states": self.from_states,
            "required_gates": self.required_gates,
            "non_waivable_gates": self.non_waivable_gates,
        }.items():
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must not contain duplicates")
        if not set(self.non_waivable_gates).issubset(self.required_gates):
            raise ValueError("Non-waivable gates must be required gates")
        if self.waiver_mode == "FORBIDDEN" and self.waived_to_state is not None:
            raise ValueError("FORBIDDEN waiver mode cannot define waived_to_state")
        if self.waiver_mode != "FORBIDDEN" and not self.waived_to_state:
            raise ValueError("Waiver-enabled policy must define waived_to_state")
        if self.waiver_mode != "FORBIDDEN" and not self.waivable_gates:
            raise ValueError("Waiver-enabled policy must declare at least one waivable gate")
        has_alias_side_effect = self.side_effects.mlflow_champion_alias is not None
        if self.target_type == "model_version" and not has_alias_side_effect:
            raise ValueError("Model promotion must define MLflow alias side effects")
        if self.target_type == "release" and has_alias_side_effect:
            raise ValueError("Release promotion cannot mutate MLflow aliases")
        if self.target_type == "model_version" and self.waiver_mode != "FORBIDDEN":
            raise ValueError("Champion model promotion cannot use waivers")
        return self

    @property
    def waivable_gates(self) -> frozenset[str]:
        if self.waiver_mode == "FORBIDDEN":
            return frozenset()
        return frozenset(self.required_gates) - frozenset(self.non_waivable_gates)


class PromotionPolicyCatalog(StrictModel):
    schema_version: Literal["promotion_policies_v1"]
    status: Literal["ACTIVE"]
    policies: tuple[PromotionPolicy, ...]

    @model_validator(mode="after")
    def unique_policies(self) -> "PromotionPolicyCatalog":
        ids = [item.policy_id for item in self.policies]
        if len(ids) != len(set(ids)):
            raise ValueError("Promotion policy IDs must be unique")
        kinds: set[tuple[str, str]] = set()
        for policy in self.policies:
            for kind in policy.target_kinds:
                key = (policy.target_type, kind)
                if key in kinds:
                    raise ValueError(f"Duplicate promotion target mapping: {key}")
                kinds.add(key)
        return self

    def by_id(self) -> dict[str, PromotionPolicy]:
        return {item.policy_id: item for item in self.policies}

    def for_target(self, target_type: str, target_kind: str) -> PromotionPolicy:
        matches = [
            policy
            for policy in self.policies
            if policy.target_type == target_type and target_kind in policy.target_kinds
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one promotion policy for {target_type}/{target_kind}; "
                f"found {len(matches)}"
            )
        return matches[0]


@lru_cache(maxsize=1)
def load_promotion_policies() -> PromotionPolicyCatalog:
    path = project_root() / "config/platform/promotion_policies_v1.json"
    return PromotionPolicyCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def promotion_policy_sha256(path: Path | None = None) -> str:
    source = path or project_root() / "config/platform/promotion_policies_v1.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
