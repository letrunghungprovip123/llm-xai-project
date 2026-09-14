"""Dataset-neutral contracts for the multi-dataset credit-risk pipeline.

This module is intentionally dependency-light.  It introduces the canonical
scientific boundary without changing any legacy Home Credit stage behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


SUPPORTED_TASK_TYPES = {"binary_classification"}
SUPPORTED_DOMAINS = {"credit_risk"}


def _require_non_empty(value: Any, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


@dataclass(frozen=True)
class EntityContract:
    entity_type: str
    source_id_column: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EntityContract":
        payload = _require_mapping(payload, "entity")
        return cls(
            entity_type=_require_non_empty(payload.get("entity_type"), "entity.entity_type"),
            source_id_column=_require_non_empty(
                payload.get("source_id_column"), "entity.source_id_column"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "source_id_column": self.source_id_column,
        }




@dataclass(frozen=True)
class PredictionSemanticsContract:
    """User-facing and validator-facing semantics for a binary credit-risk target.

    These fields deliberately describe *meaning*, not raw dataset columns.  The
    defaults preserve the historical Home Credit vocabulary so older profiles
    remain valid, while new datasets can supply endpoint-specific labels and
    phrases without changing common LLM/validation code.
    """

    positive_label: str = "high_default_risk"
    negative_label: str = "low_default_risk"
    prediction_subject: str = "rủi ro tín dụng"
    positive_display_name: str = "rủi ro tín dụng cao"
    negative_display_name: str = "rủi ro tín dụng thấp"
    positive_direction_phrase: str = "rủi ro cao"
    negative_direction_phrase: str = "rủi ro thấp"

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any] | None
    ) -> "PredictionSemanticsContract":
        if payload is None:
            return cls()
        payload = _require_mapping(payload, "target.prediction_semantics")
        defaults = cls()
        return cls(
            positive_label=_require_non_empty(
                payload.get("positive_label", defaults.positive_label),
                "target.prediction_semantics.positive_label",
            ),
            negative_label=_require_non_empty(
                payload.get("negative_label", defaults.negative_label),
                "target.prediction_semantics.negative_label",
            ),
            prediction_subject=_require_non_empty(
                payload.get("prediction_subject", defaults.prediction_subject),
                "target.prediction_semantics.prediction_subject",
            ),
            positive_display_name=_require_non_empty(
                payload.get("positive_display_name", defaults.positive_display_name),
                "target.prediction_semantics.positive_display_name",
            ),
            negative_display_name=_require_non_empty(
                payload.get("negative_display_name", defaults.negative_display_name),
                "target.prediction_semantics.negative_display_name",
            ),
            positive_direction_phrase=_require_non_empty(
                payload.get("positive_direction_phrase", defaults.positive_direction_phrase),
                "target.prediction_semantics.positive_direction_phrase",
            ),
            negative_direction_phrase=_require_non_empty(
                payload.get("negative_direction_phrase", defaults.negative_direction_phrase),
                "target.prediction_semantics.negative_direction_phrase",
            ),
        )

    def __post_init__(self) -> None:
        if self.positive_label == self.negative_label:
            raise ValueError(
                "target prediction positive_label and negative_label must differ"
            )
        if self.positive_display_name == self.negative_display_name:
            raise ValueError(
                "target prediction positive/negative display names must differ"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "positive_label": self.positive_label,
            "negative_label": self.negative_label,
            "prediction_subject": self.prediction_subject,
            "positive_display_name": self.positive_display_name,
            "negative_display_name": self.negative_display_name,
            "positive_direction_phrase": self.positive_direction_phrase,
            "negative_direction_phrase": self.negative_direction_phrase,
        }

    def to_prompt_dict(self) -> dict[str, Any]:
        """Return only semantics safe and useful for an LLM prompt."""
        return self.to_dict()


@dataclass(frozen=True)
class TargetContract:
    source_column: str
    canonical_name: str
    positive_value: Any
    negative_value: Any
    semantic_name: str
    prediction_horizon: str | None = None
    prediction_semantics: PredictionSemanticsContract | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TargetContract":
        payload = _require_mapping(payload, "target")
        if "positive_value" not in payload or "negative_value" not in payload:
            raise ValueError("target must define positive_value and negative_value")
        if payload["positive_value"] == payload["negative_value"]:
            raise ValueError("target positive_value and negative_value must differ")
        horizon = payload.get("prediction_horizon")
        if horizon is not None:
            horizon = _require_non_empty(horizon, "target.prediction_horizon")
        return cls(
            source_column=_require_non_empty(payload.get("source_column"), "target.source_column"),
            canonical_name=_require_non_empty(
                payload.get("canonical_name", "target"), "target.canonical_name"
            ),
            positive_value=payload["positive_value"],
            negative_value=payload["negative_value"],
            semantic_name=_require_non_empty(payload.get("semantic_name"), "target.semantic_name"),
            prediction_horizon=horizon,
            prediction_semantics=(
                PredictionSemanticsContract.from_dict(payload.get("prediction_semantics"))
                if payload.get("prediction_semantics") is not None
                else None
            ),
        )

    @property
    def effective_prediction_semantics(self) -> PredictionSemanticsContract:
        return self.prediction_semantics or PredictionSemanticsContract()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_column": self.source_column,
            "canonical_name": self.canonical_name,
            "positive_value": self.positive_value,
            "negative_value": self.negative_value,
            "semantic_name": self.semantic_name,
            "prediction_horizon": self.prediction_horizon,
        }
        if self.prediction_semantics is not None:
            payload["prediction_semantics"] = self.prediction_semantics.to_dict()
        return payload

    def semantic_payload(self, *, include_source_values: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "canonical_name": self.canonical_name,
            "semantic_name": self.semantic_name,
            "prediction_horizon": self.prediction_horizon,
            "positive_class": 1,
            "negative_class": 0,
            **self.effective_prediction_semantics.to_prompt_dict(),
        }
        if include_source_values:
            payload.update(
                {
                    "source_positive_value": self.positive_value,
                    "source_negative_value": self.negative_value,
                }
            )
        return payload


@dataclass(frozen=True)
class DatasetCapabilities:
    supports_stratified_split: bool = True
    supports_feature_level_xai: bool = True
    supports_semantic_registry: bool = True
    supports_case_strata: bool = True
    supports_adaptive_evidence: bool = True
    has_stable_entity_id: bool = True
    feature_count: int | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "DatasetCapabilities":
        payload = {} if payload is None else _require_mapping(payload, "capabilities")
        feature_count = payload.get("feature_count")
        if feature_count is not None:
            feature_count = int(feature_count)
            if feature_count <= 0:
                raise ValueError("capabilities.feature_count must be > 0 when provided")
        return cls(
            supports_stratified_split=bool(payload.get("supports_stratified_split", True)),
            supports_feature_level_xai=bool(payload.get("supports_feature_level_xai", True)),
            supports_semantic_registry=bool(payload.get("supports_semantic_registry", True)),
            supports_case_strata=bool(payload.get("supports_case_strata", True)),
            supports_adaptive_evidence=bool(payload.get("supports_adaptive_evidence", True)),
            has_stable_entity_id=bool(payload.get("has_stable_entity_id", True)),
            feature_count=feature_count,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "supports_stratified_split": self.supports_stratified_split,
            "supports_feature_level_xai": self.supports_feature_level_xai,
            "supports_semantic_registry": self.supports_semantic_registry,
            "supports_case_strata": self.supports_case_strata,
            "supports_adaptive_evidence": self.supports_adaptive_evidence,
            "has_stable_entity_id": self.has_stable_entity_id,
            "feature_count": self.feature_count,
        }


@dataclass(frozen=True)
class AdapterContract:
    adapter_id: str
    adapter_version: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AdapterContract":
        payload = _require_mapping(payload, "adapter")
        return cls(
            adapter_id=_require_non_empty(payload.get("adapter_id"), "adapter.adapter_id"),
            adapter_version=_require_non_empty(
                payload.get("adapter_version"), "adapter.adapter_version"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
        }


@dataclass(frozen=True)
class DatasetProfile:
    schema_version: str
    dataset_id: str
    dataset_version: str
    domain: str
    task_type: str
    entity: EntityContract
    target: TargetContract
    adapter: AdapterContract
    capabilities: DatasetCapabilities

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DatasetProfile":
        payload = _require_mapping(payload, "dataset profile")
        schema_version = _require_non_empty(payload.get("schema_version"), "schema_version")
        if schema_version != "dataset_profile_v1":
            raise ValueError(f"Unsupported dataset profile schema_version: {schema_version}")
        domain = _require_non_empty(payload.get("domain"), "domain")
        task_type = _require_non_empty(payload.get("task_type"), "task_type")
        if domain not in SUPPORTED_DOMAINS:
            raise ValueError(f"Unsupported domain for v1 common pipeline: {domain}")
        if task_type not in SUPPORTED_TASK_TYPES:
            raise ValueError(f"Unsupported task_type for v1 common pipeline: {task_type}")
        profile = cls(
            schema_version=schema_version,
            dataset_id=_require_non_empty(payload.get("dataset_id"), "dataset_id"),
            dataset_version=_require_non_empty(payload.get("dataset_version"), "dataset_version"),
            domain=domain,
            task_type=task_type,
            entity=EntityContract.from_dict(payload.get("entity", {})),
            target=TargetContract.from_dict(payload.get("target", {})),
            adapter=AdapterContract.from_dict(payload.get("adapter", {})),
            capabilities=DatasetCapabilities.from_dict(payload.get("capabilities")),
        )
        if profile.entity.source_id_column == profile.target.source_column:
            raise ValueError("entity source ID column cannot be the target column")
        return profile

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "domain": self.domain,
            "task_type": self.task_type,
            "entity": self.entity.to_dict(),
            "target": self.target.to_dict(),
            "adapter": self.adapter.to_dict(),
            "capabilities": self.capabilities.to_dict(),
        }


@dataclass(frozen=True)
class ExperimentProfile:
    schema_version: str
    experiment_id: str
    dataset_id: str
    case_strata: tuple[str, ...]
    cases_per_stratum: int
    evidence_conditions: tuple[str, ...]
    llm_count: int
    expected_planned_generations: int

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExperimentProfile":
        payload = _require_mapping(payload, "experiment profile")
        schema_version = _require_non_empty(payload.get("schema_version"), "schema_version")
        if schema_version != "experiment_profile_v1":
            raise ValueError(f"Unsupported experiment profile schema_version: {schema_version}")
        case_strata = tuple(str(item).strip() for item in payload.get("case_strata", []))
        evidence_conditions = tuple(
            str(item).strip() for item in payload.get("evidence_conditions", [])
        )
        if not case_strata or any(not item for item in case_strata):
            raise ValueError("experiment case_strata must be non-empty")
        if not evidence_conditions or any(not item for item in evidence_conditions):
            raise ValueError("experiment evidence_conditions must be non-empty")
        cases_per_stratum = int(payload.get("cases_per_stratum", 0))
        llm_count = int(payload.get("llm_count", 0))
        expected = int(payload.get("expected_planned_generations", 0))
        if cases_per_stratum <= 0 or llm_count <= 0 or expected <= 0:
            raise ValueError("experiment counts must be positive")
        computed = len(case_strata) * cases_per_stratum * len(evidence_conditions) * llm_count
        if expected != computed:
            raise ValueError(
                "expected_planned_generations must equal "
                "len(case_strata) * cases_per_stratum * len(evidence_conditions) * llm_count "
                f"({computed})"
            )
        return cls(
            schema_version=schema_version,
            experiment_id=_require_non_empty(payload.get("experiment_id"), "experiment_id"),
            dataset_id=_require_non_empty(payload.get("dataset_id"), "dataset_id"),
            case_strata=case_strata,
            cases_per_stratum=cases_per_stratum,
            evidence_conditions=evidence_conditions,
            llm_count=llm_count,
            expected_planned_generations=expected,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "dataset_id": self.dataset_id,
            "case_strata": list(self.case_strata),
            "cases_per_stratum": self.cases_per_stratum,
            "evidence_conditions": list(self.evidence_conditions),
            "llm_count": self.llm_count,
            "expected_planned_generations": self.expected_planned_generations,
        }


@dataclass(frozen=True)
class ArtifactReference:
    path: str
    sha256: str
    required: bool = True

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactReference":
        payload = _require_mapping(payload, "artifact reference")
        digest = _require_non_empty(payload.get("sha256"), "artifact.sha256")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest.lower()):
            raise ValueError("artifact.sha256 must be a 64-character hexadecimal digest")
        return cls(
            path=_require_non_empty(payload.get("path"), "artifact.path"),
            sha256=digest.lower(),
            required=bool(payload.get("required", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "required": self.required}


@dataclass(frozen=True)
class CanonicalDatasetBundle:
    schema_version: str
    dataset_id: str
    dataset_version: str
    dataset_fingerprint: str
    dataset_profile_sha256: str
    artifacts: Mapping[str, ArtifactReference]
    provenance: Mapping[str, Any]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CanonicalDatasetBundle":
        payload = _require_mapping(payload, "canonical dataset bundle")
        schema_version = _require_non_empty(payload.get("schema_version"), "schema_version")
        if schema_version != "canonical_dataset_bundle_v1":
            raise ValueError(f"Unsupported canonical bundle schema_version: {schema_version}")
        fingerprint = _require_non_empty(payload.get("dataset_fingerprint"), "dataset_fingerprint")
        if len(fingerprint) != 64:
            raise ValueError("dataset_fingerprint must be a SHA-256 hex digest")
        profile_sha = _require_non_empty(
            payload.get("dataset_profile_sha256"), "dataset_profile_sha256"
        )
        if len(profile_sha) != 64:
            raise ValueError("dataset_profile_sha256 must be a SHA-256 hex digest")
        raw_artifacts = _require_mapping(payload.get("artifacts", {}), "artifacts")
        artifacts = {
            str(name): ArtifactReference.from_dict(reference)
            for name, reference in raw_artifacts.items()
        }
        required_names = {
            "feature_matrix",
            "target",
            "feature_registry_csv",
            "feature_registry_yaml",
            "concept_registry_yaml",
        }
        missing = sorted(required_names - set(artifacts))
        if missing:
            raise ValueError(f"canonical bundle missing required artifact references: {missing}")
        provenance = _require_mapping(payload.get("provenance", {}), "provenance")
        return cls(
            schema_version=schema_version,
            dataset_id=_require_non_empty(payload.get("dataset_id"), "dataset_id"),
            dataset_version=_require_non_empty(payload.get("dataset_version"), "dataset_version"),
            dataset_fingerprint=fingerprint.lower(),
            dataset_profile_sha256=profile_sha.lower(),
            artifacts=artifacts,
            provenance=dict(provenance),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_fingerprint": self.dataset_fingerprint,
            "dataset_profile_sha256": self.dataset_profile_sha256,
            "artifacts": {name: ref.to_dict() for name, ref in self.artifacts.items()},
            "provenance": dict(self.provenance),
        }

    def resolve_artifact(self, name: str, project_root: Path) -> Path:
        if name not in self.artifacts:
            raise KeyError(name)
        path = Path(self.artifacts[name].path)
        return path if path.is_absolute() else project_root / path
