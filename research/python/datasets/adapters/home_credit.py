"""Compatibility adapter for the already-certified Home Credit preparation outputs.

The adapter is intentionally non-destructive: it does not re-run feature
engineering, rewrite registries, or change historical artifact identities.  It
wraps the existing Batch C outputs in the new canonical dataset contract.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...common.hashing import sha256_file
from ..root import find_repository_root
from ..contracts import ArtifactReference, CanonicalDatasetBundle, DatasetProfile
from ..profile import canonical_json_bytes, load_dataset_profile, sha256_json


REQUIRED_ARTIFACTS = {
    "feature_matrix": Path("data/processed/feature_matrix_full.parquet"),
    "target": Path("data/processed/target_full.parquet"),
    "feature_registry_csv": Path("ml/registry/feature_registry.csv"),
    "feature_registry_yaml": Path("ml/registry/feature_registry.yaml"),
    "concept_registry_yaml": Path("ml/registry/concept_registry.yaml"),
}

OPTIONAL_ARTIFACTS = {
    "raw_file_manifest": Path("data/manifests/raw_file_manifest.json"),
    "feature_matrix_summary": Path(
        "data/manifests/batch_c_feature_matrix_registry_summary.json"
    ),
    "id_columns": Path("ml/registry/id_columns.json"),
    "target_column": Path("ml/registry/target_column.json"),
    "model_feature_metadata": Path("ml/registry/model_feature_metadata.json"),
}


class HomeCreditCompatibilityAdapter:
    def __init__(
        self,
        project_root: Path | None = None,
        profile_path: Path | None = None,
        artifact_root: Path | None = None,
    ) -> None:
        self.project_root = (
            find_repository_root(Path(__file__)) if project_root is None else project_root.resolve()
        )
        self.profile_path = (
            self.project_root / "config/research/datasets/home_credit_v1.json"
            if profile_path is None
            else profile_path.resolve()
        )
        # Historical prepared artifacts may live in an older sibling worktree.
        # Keep the current project/profile root separate from the read-only
        # artifact locator so compatibility wrapping never requires copying or
        # rewriting certified outputs.
        self.artifact_root = (
            self.project_root if artifact_root is None else artifact_root.resolve()
        )
        self.profile: DatasetProfile = load_dataset_profile(self.profile_path)
        if self.profile.adapter.adapter_id != "home_credit":
            raise ValueError("HomeCreditCompatibilityAdapter requires adapter_id=home_credit")

    def _resolve(self, relative_path: Path) -> Path:
        return self.artifact_root / relative_path

    def validate_source(self) -> dict[str, object]:
        missing_required = [
            str(path)
            for path in REQUIRED_ARTIFACTS.values()
            if not self._resolve(path).is_file()
        ]
        missing_optional = [
            str(path)
            for path in OPTIONAL_ARTIFACTS.values()
            if not self._resolve(path).is_file()
        ]
        return {
            "status": "passed" if not missing_required else "blocked",
            "artifact_root": str(self.artifact_root),
            "missing_required": missing_required,
            "missing_optional": missing_optional,
        }

    def _dataset_fingerprint(self, artifact_hashes: dict[str, str]) -> tuple[str, str]:
        raw_manifest_path = self._resolve(OPTIONAL_ARTIFACTS["raw_file_manifest"])
        if raw_manifest_path.is_file():
            payload = json.loads(raw_manifest_path.read_text(encoding="utf-8"))
            raw_files = payload.get("raw_files", {})
            stable_raw_files = {
                name: metadata.get("sha256")
                for name, metadata in sorted(raw_files.items())
                if isinstance(metadata, dict) and metadata.get("sha256")
            }
            if stable_raw_files:
                fingerprint = sha256_json(
                    {
                        "dataset_id": self.profile.dataset_id,
                        "dataset_version": self.profile.dataset_version,
                        "raw_files": stable_raw_files,
                    }
                )
                return fingerprint, "raw_manifest_sha256_set_v1"

        fingerprint = sha256_json(
            {
                "dataset_id": self.profile.dataset_id,
                "dataset_version": self.profile.dataset_version,
                "prepared_artifact_hashes": artifact_hashes,
            }
        )
        return fingerprint, "prepared_artifact_hash_fallback_v1"

    def build_canonical_bundle(
        self,
        output_path: Path | None = None,
    ) -> CanonicalDatasetBundle:
        validation = self.validate_source()
        if validation["status"] != "passed":
            raise FileNotFoundError(
                "Home Credit compatibility adapter is missing required historical outputs: "
                f"{validation['missing_required']}"
            )

        references: dict[str, ArtifactReference] = {}
        hashes: dict[str, str] = {}
        for name, relative_path in REQUIRED_ARTIFACTS.items():
            digest = sha256_file(self._resolve(relative_path))
            hashes[name] = digest
            references[name] = ArtifactReference(
                path=relative_path.as_posix(),
                sha256=digest,
                required=True,
            )

        for name, relative_path in OPTIONAL_ARTIFACTS.items():
            resolved = self._resolve(relative_path)
            if resolved.is_file():
                digest = sha256_file(resolved)
                hashes[name] = digest
                references[name] = ArtifactReference(
                    path=relative_path.as_posix(),
                    sha256=digest,
                    required=False,
                )

        profile_payload = self.profile.to_dict()
        profile_sha256 = hashlib.sha256(canonical_json_bytes(profile_payload)).hexdigest()
        dataset_fingerprint, fingerprint_method = self._dataset_fingerprint(hashes)

        bundle = CanonicalDatasetBundle(
            schema_version="canonical_dataset_bundle_v1",
            dataset_id=self.profile.dataset_id,
            dataset_version=self.profile.dataset_version,
            dataset_fingerprint=dataset_fingerprint,
            dataset_profile_sha256=profile_sha256,
            artifacts=references,
            provenance={
                "adapter_id": self.profile.adapter.adapter_id,
                "adapter_version": self.profile.adapter.adapter_version,
                "fingerprint_method": fingerprint_method,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "historical_outputs_wrapped_without_rewrite": True,
                "artifact_source_root_locator": str(self.artifact_root),
                "artifact_paths_relative_to_source_root": True,
            },
        )

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(bundle.to_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        return bundle
