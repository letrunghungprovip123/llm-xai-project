from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..common_ml.context import CommonMLRunContext
from ..datasets.execution import DatasetExecutionContext


@dataclass(frozen=True)
class CommonXAIRunContext:
    source_ml: CommonMLRunContext
    execution: DatasetExecutionContext

    @classmethod
    def load(
        cls,
        *,
        dataset_profile_path: Path,
        canonical_bundle_path: Path,
        experiment_id: str,
        source_run_id: str,
        run_id: str,
        project_root: Path | None = None,
        artifact_root: Path | None = None,
    ) -> "CommonXAIRunContext":
        source = CommonMLRunContext.load(
            dataset_profile_path=dataset_profile_path,
            canonical_bundle_path=canonical_bundle_path,
            experiment_id=experiment_id,
            run_id=source_run_id,
            project_root=project_root,
            artifact_root=artifact_root,
        )
        execution = DatasetExecutionContext(
            project_root=source.project_root,
            dataset_id=source.profile.dataset_id,
            experiment_id=experiment_id,
            run_id=run_id,
        )
        ctx = cls(source_ml=source, execution=execution)
        ctx.validate_source_ml()
        return ctx

    @property
    def profile(self):
        return self.source_ml.profile

    @property
    def bundle(self):
        return self.source_ml.bundle

    @property
    def source_paths(self):
        return self.source_ml.paths

    @property
    def paths(self):
        return self.execution.paths

    @property
    def experiment_id(self) -> str:
        return self.execution.experiment_id

    @property
    def run_id(self) -> str:
        return self.execution.run_id

    @property
    def source_run_id(self) -> str:
        return self.source_ml.run_id

    def validate_source_ml(self) -> None:
        required = [
            self.source_paths.manifest_dir / "common_ml_model_training_manifest.json",
            self.source_paths.artifact_dir / "models" / "best_model.joblib",
            self.source_paths.registry_dir / "model_registry.json",
            self.source_paths.report_dir / "model_predictions_test.csv",
        ]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                "Common XAI requires a completed common-ML modeling run. Missing: "
                + ", ".join(missing)
            )

    def create_workspace(self) -> None:
        self.execution.create_output_directories()
        for path in (
            self.paths.report_dir / "xai",
            self.paths.report_dir / "xai_quality",
            self.paths.report_dir / "explanation_ir_v3",
            self.paths.report_dir / "evidence_exposure",
        ):
            path.mkdir(parents=True, exist_ok=True)

    def provenance(self) -> dict[str, object]:
        return {
            "dataset_id": self.profile.dataset_id,
            "dataset_version": self.profile.dataset_version,
            "dataset_fingerprint": self.bundle.dataset_fingerprint,
            "dataset_profile_sha256": self.bundle.dataset_profile_sha256,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "source_common_ml_run_id": self.source_run_id,
            "workspace_root": str(self.execution.workspace_root),
            "source_common_ml_workspace_root": str(self.source_ml.execution.workspace_root),
        }
