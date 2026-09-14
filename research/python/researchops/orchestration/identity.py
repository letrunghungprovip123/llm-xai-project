from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from research.python.researchops.artifacts.models import ArtifactManifestV3
from research.python.researchops.orchestration.flow_catalog.models import FlowDefinition
from research.python.researchops.stage_registry.models import StageDefinition


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_payload(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True)
class ArtifactIdentity:
    artifact_id: str
    artifact_type: str
    manifest_sha256: str

    @classmethod
    def from_manifest(cls, manifest: ArtifactManifestV3) -> "ArtifactIdentity":
        return cls(
            artifact_id=manifest.artifact_id,
            artifact_type=manifest.artifact_type,
            manifest_sha256=manifest.manifest_sha256,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "manifest_sha256": self.manifest_sha256,
        }


def flow_orchestration_key(
    *,
    flow: FlowDefinition,
    flow_catalog_sha256: str,
    stage_registry_sha256: str,
    input_artifacts: Mapping[str, ArtifactIdentity],
    parameters: Mapping[str, Any],
    source_commit: str,
    dependency_lock_sha256: str,
) -> str:
    return sha256_payload(
        {
            "schema_version": "flow_orchestration_identity_v1",
            "flow_catalog_sha256": flow_catalog_sha256,
            "stage_registry_sha256": stage_registry_sha256,
            "flow_id": flow.id,
            "flow_version": flow.version,
            "inputs": {
                key: input_artifacts[key].to_dict()
                for key in sorted(input_artifacts)
            },
            "parameters": dict(sorted(parameters.items())),
            "source_commit": source_commit,
            "dependency_lock_sha256": dependency_lock_sha256,
        }
    )


def stage_orchestration_key(
    *,
    flow_key: str,
    node_id: str,
    stage: StageDefinition,
    input_artifacts: Mapping[str, ArtifactIdentity],
    parameters: Mapping[str, Any],
) -> str:
    return sha256_payload(
        {
            "schema_version": "stage_orchestration_identity_v1",
            "flow_orchestration_key": flow_key,
            "node_id": node_id,
            "stage_id": stage.id,
            "stage_version": stage.version,
            "inputs": {
                key: input_artifacts[key].to_dict()
                for key in sorted(input_artifacts)
            },
            "parameters": dict(sorted(parameters.items())),
        }
    )
