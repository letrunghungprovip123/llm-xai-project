from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..common.hashing import sha256_file
from ..datasets.contracts import CanonicalDatasetBundle, DatasetProfile
from ..datasets.execution import DatasetExecutionContext
from ..datasets.profile import load_canonical_bundle, load_dataset_profile, sha256_json
from ..datasets.root import find_repository_root


@dataclass(frozen=True)
class CommonMLRunContext:
    project_root: Path
    dataset_profile_path: Path
    canonical_bundle_path: Path
    artifact_root: Path
    experiment_id: str
    run_id: str
    profile: DatasetProfile
    bundle: CanonicalDatasetBundle
    execution: DatasetExecutionContext

    @classmethod
    def load(
        cls,
        *,
        dataset_profile_path: Path,
        canonical_bundle_path: Path,
        experiment_id: str,
        run_id: str,
        project_root: Path | None = None,
        artifact_root: Path | None = None,
    ) -> "CommonMLRunContext":
        root = (
            find_repository_root(Path(__file__))
            if project_root is None
            else project_root.expanduser().resolve()
        )
        profile_path = dataset_profile_path.expanduser().resolve()
        bundle_path = canonical_bundle_path.expanduser().resolve()
        profile = load_dataset_profile(profile_path)
        bundle = load_canonical_bundle(bundle_path)

        if profile.dataset_id != bundle.dataset_id:
            raise ValueError(
                "Dataset profile and canonical bundle dataset_id differ: "
                f"{profile.dataset_id!r} != {bundle.dataset_id!r}"
            )
        if profile.dataset_version != bundle.dataset_version:
            raise ValueError(
                "Dataset profile and canonical bundle dataset_version differ: "
                f"{profile.dataset_version!r} != {bundle.dataset_version!r}"
            )
        expected_profile_sha = sha256_json(profile.to_dict())
        if expected_profile_sha != bundle.dataset_profile_sha256:
            raise ValueError(
                "Dataset profile SHA-256 does not match canonical bundle. "
                "Refuse to run with mismatched scientific contracts."
            )

        resolved_artifact_root = cls._resolve_artifact_root(
            project_root=root,
            bundle=bundle,
            explicit=artifact_root,
        )
        execution = DatasetExecutionContext(
            project_root=root,
            dataset_id=profile.dataset_id,
            experiment_id=experiment_id,
            run_id=run_id,
        )
        return cls(
            project_root=root,
            dataset_profile_path=profile_path,
            canonical_bundle_path=bundle_path,
            artifact_root=resolved_artifact_root,
            experiment_id=experiment_id,
            run_id=run_id,
            profile=profile,
            bundle=bundle,
            execution=execution,
        )

    @staticmethod
    def _resolve_artifact_root(
        *,
        project_root: Path,
        bundle: CanonicalDatasetBundle,
        explicit: Path | None,
    ) -> Path:
        if explicit is not None:
            return explicit.expanduser().resolve()
        locator = str(bundle.provenance.get("artifact_source_root_locator", "")).strip()
        if locator:
            return Path(locator).expanduser().resolve()
        return project_root

    @property
    def paths(self):
        return self.execution.paths

    @property
    def canonical_target_column(self) -> str:
        return self.profile.target.canonical_name

    @property
    def source_id_column(self) -> str:
        return self.profile.entity.source_id_column

    @property
    def source_target_column(self) -> str:
        return self.profile.target.source_column

    def resolve_bundle_artifact(self, name: str, *, verify_hash: bool = True) -> Path:
        if name not in self.bundle.artifacts:
            raise KeyError(f"Canonical bundle has no artifact named {name!r}")
        reference = self.bundle.artifacts[name]
        path = Path(reference.path)
        resolved = path if path.is_absolute() else self.artifact_root / path
        if reference.required and not resolved.is_file():
            raise FileNotFoundError(f"Missing required canonical artifact {name}: {resolved}")
        if verify_hash and resolved.is_file():
            digest = sha256_file(resolved)
            if digest != reference.sha256:
                raise ValueError(
                    f"SHA-256 mismatch for canonical artifact {name}: "
                    f"expected={reference.sha256}, actual={digest}, path={resolved}"
                )
        return resolved

    def create_workspace(self) -> None:
        self.execution.create_output_directories()
        (self.paths.processed_dir / "splits").mkdir(parents=True, exist_ok=True)
        (self.paths.processed_dir / "model_ready" / "tree").mkdir(parents=True, exist_ok=True)
        (self.paths.processed_dir / "model_ready" / "linear").mkdir(parents=True, exist_ok=True)
        (self.paths.artifact_dir / "preprocessing").mkdir(parents=True, exist_ok=True)
        (self.paths.artifact_dir / "models").mkdir(parents=True, exist_ok=True)

    def common_provenance(self) -> dict[str, object]:
        return {
            "dataset_id": self.profile.dataset_id,
            "dataset_version": self.profile.dataset_version,
            "dataset_fingerprint": self.bundle.dataset_fingerprint,
            "dataset_profile_sha256": self.bundle.dataset_profile_sha256,
            "canonical_bundle_schema_version": self.bundle.schema_version,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "workspace_root": str(self.execution.workspace_root),
        }
