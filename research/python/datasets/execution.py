"""Dataset-scoped runtime context.

This is additive infrastructure only. Legacy stages keep using their existing
DEFAULT_PATHS until each stage is deliberately migrated behind a regression gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def _safe_segment(value: str, field_name: str) -> str:
    value = str(value).strip()
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"{field_name} must be a single safe path segment")
    return value


@dataclass(frozen=True)
class ScopedResearchPaths:
    """Research path layout rooted inside one isolated run workspace."""

    workspace_root: Path

    @property
    def raw_dir(self) -> Path:
        return self.workspace_root / "data" / "raw"

    @property
    def interim_dir(self) -> Path:
        return self.workspace_root / "data" / "interim"

    @property
    def processed_dir(self) -> Path:
        return self.workspace_root / "data" / "processed"

    @property
    def report_dir(self) -> Path:
        return self.workspace_root / "data" / "reports"

    @property
    def manifest_dir(self) -> Path:
        return self.workspace_root / "data" / "manifests"

    @property
    def registry_dir(self) -> Path:
        return self.workspace_root / "ml" / "registry"

    @property
    def artifact_dir(self) -> Path:
        return self.workspace_root / "artifacts"


@dataclass(frozen=True)
class DatasetExecutionContext:
    project_root: Path
    dataset_id: str
    experiment_id: str
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_root", self.project_root.resolve())
        _safe_segment(self.dataset_id, "dataset_id")
        _safe_segment(self.experiment_id, "experiment_id")
        _safe_segment(self.run_id, "run_id")

    @property
    def workspace_root(self) -> Path:
        return (
            self.project_root
            / ".researchops"
            / "workspaces"
            / self.dataset_id
            / self.experiment_id
            / self.run_id
        )

    @property
    def paths(self) -> ScopedResearchPaths:
        return ScopedResearchPaths(self.workspace_root)

    def create_output_directories(self) -> None:
        paths = self.paths
        for path in (
            paths.raw_dir,
            paths.interim_dir,
            paths.processed_dir,
            paths.report_dir,
            paths.manifest_dir,
            paths.registry_dir,
            paths.artifact_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
