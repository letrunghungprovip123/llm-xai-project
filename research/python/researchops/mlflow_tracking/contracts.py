from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from research.python.researchops.contracts.io import project_root


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExperimentDefinition(StrictModel):
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)


class ExperimentCatalog(StrictModel):
    schema_version: Literal["mlflow_experiments_v1"]
    status: Literal["ACTIVE"]
    experiments: tuple[ExperimentDefinition, ...]
    default_tags: dict[str, str]

    @model_validator(mode="after")
    def unique_names(self) -> "ExperimentCatalog":
        names = [item.name for item in self.experiments]
        if len(names) != len(set(names)):
            raise ValueError("Experiment names must be unique")
        return self


class TrackingContract(StrictModel):
    schema_version: Literal["mlflow_tracking_contract_v1"]
    status: Literal["ACTIVE"]
    mlflow_version: str
    training_experiment: str
    registered_model_name: str
    tracking_key_version: Literal["tracking_key_v1"]
    run_structure: Literal["parent_with_model_children"]
    required_run_tags: tuple[str, ...]
    required_training_parameters: tuple[str, ...]
    metric_mapping: dict[str, str]
    integration_states: tuple[str, ...]
    stable_status_values: tuple[str, ...]

    @field_validator("required_run_tags", "required_training_parameters", "integration_states", "stable_status_values")
    @classmethod
    def unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("Contract lists must not contain duplicates")
        return values

    @model_validator(mode="after")
    def required_states_exist(self) -> "TrackingContract":
        required = {"DISCOVERED", "COMPLETE", "FAILED_RECONCILIATION"}
        missing = required - set(self.integration_states)
        if missing:
            raise ValueError(f"Missing integration states: {sorted(missing)}")
        if "researchops.tracking_key" not in self.required_run_tags:
            raise ValueError("Tracking key tag is mandatory")
        return self


class RegistryPolicy(StrictModel):
    schema_version: Literal["mlflow_registry_policy_v1"]
    status: Literal["ACTIVE"]
    registered_model_name: str
    aliases: tuple[str, ...]
    candidate_selection_source: str
    promotion_requirements: tuple[str, ...]
    non_waivable_requirements: tuple[str, ...]
    training_code_may_assign_champion: Literal[False]

    @model_validator(mode="after")
    def policy_is_safe(self) -> "RegistryPolicy":
        required_aliases = {"candidate", "champion", "archived-reference"}
        if set(self.aliases) != required_aliases:
            raise ValueError("Registry aliases must match the governed v1 set")
        if not set(self.non_waivable_requirements).issubset(self.promotion_requirements):
            raise ValueError("Non-waivable requirements must be promotion requirements")
        return self


def _read(relative: str) -> dict:
    path = project_root() / relative
    return json.loads(path.read_text(encoding="utf-8"))


def load_experiment_catalog() -> ExperimentCatalog:
    return ExperimentCatalog.model_validate(_read("config/platform/mlflow/mlflow_experiments_v1.json"))


def load_tracking_contract() -> TrackingContract:
    return TrackingContract.model_validate(_read("config/platform/mlflow/mlflow_tracking_contract_v1.json"))


def load_registry_policy() -> RegistryPolicy:
    return RegistryPolicy.model_validate(_read("config/platform/mlflow/mlflow_registry_policy_v1.json"))


def validate_contract_set() -> dict[str, object]:
    experiments = load_experiment_catalog()
    tracking = load_tracking_contract()
    registry = load_registry_policy()
    names = {item.name for item in experiments.experiments}
    if tracking.training_experiment not in names:
        raise ValueError("Training experiment is missing from the experiment catalog")
    if tracking.registered_model_name != registry.registered_model_name:
        raise ValueError("Tracking and registry model names disagree")
    if tracking.mlflow_version != "3.14.0":
        raise ValueError("Phase 5 contract must pin MLflow 3.14.0")
    return {
        "schema_version": "mlflow_contract_validation_v1",
        "passed": True,
        "experiment_count": len(experiments.experiments),
        "training_experiment": tracking.training_experiment,
        "registered_model_name": registry.registered_model_name,
        "mlflow_version": tracking.mlflow_version,
    }
