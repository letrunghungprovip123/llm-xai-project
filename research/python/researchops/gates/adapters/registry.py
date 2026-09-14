from __future__ import annotations

from .base import GateAdapter
from .builtin import (
    ClaimValidationReleaseAdapter,
    DashboardCertificationAdapter,
    GenerationManifestAdapter,
    ManifestStatusAdapter,
    MLflowRegistrationReceiptAdapter,
    ModelReadyReportAdapter,
    ModelTrainingManifestAdapter,
    StandardCheckReportAdapter,
    XAIQualityReportAdapter,
)


class GateAdapterRegistry:
    def __init__(self) -> None:
        adapters: tuple[GateAdapter, ...] = (
            ManifestStatusAdapter("execution_success_v1"),
            ManifestStatusAdapter("manifest_status_v1"),
            ModelTrainingManifestAdapter(),
            ModelReadyReportAdapter("model_ready_report_v1"),
            ManifestStatusAdapter("xai_manifest_v1"),
            XAIQualityReportAdapter("xai_quality_report_v1"),
            GenerationManifestAdapter("generation_manifest_v1"),
            StandardCheckReportAdapter(),
            DashboardCertificationAdapter(),
            ManifestStatusAdapter("environment_verification_v1"),
            ManifestStatusAdapter("complete_release_bundle_v1"),
            ManifestStatusAdapter("artifact_integrity_v1"),
            ClaimValidationReleaseAdapter(),
            MLflowRegistrationReceiptAdapter(),
        )
        self._adapters = {
            (item.adapter_id, item.adapter_version): item for item in adapters
        }

    def get(self, adapter_id: str, version: int) -> GateAdapter:
        try:
            return self._adapters[(adapter_id, version)]
        except KeyError as exc:
            raise ValueError(f"Unknown gate adapter: {adapter_id}@{version}") from exc

    def identities(self) -> set[tuple[str, int]]:
        return set(self._adapters)
