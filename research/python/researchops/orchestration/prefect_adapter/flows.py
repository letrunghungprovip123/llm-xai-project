from __future__ import annotations

from typing import Any

from .flow_engine import execute_catalog_flow
from ..approvals.prefect_boundary import PrefectApprovalBoundary

try:
    from prefect import flow
except ImportError:  # deterministic contract tests do not require Prefect import
    flow = None


def _execute(
    flow_id: str,
    input_artifact_ids: dict[str, str] | None = None,
    parameters: dict[str, Any] | None = None,
    requested_by: str = "prefect-user",
) -> dict[str, Any]:
    return execute_catalog_flow(
        flow_id=flow_id,
        input_artifact_ids=input_artifact_ids,
        parameters=parameters,
        requested_by=requested_by,
        approval_boundary=PrefectApprovalBoundary(),
    ).model_dump(mode="json")


def _missing_prefect(*args: Any, **kwargs: Any) -> dict[str, Any]:
    del args, kwargs
    raise RuntimeError("Prefect is required to execute deployed flows")


if flow is None:
    verify_source_environment = _missing_prefect
    train_model_release = _missing_prefect
    register_verified_training_release = _missing_prefect
    build_xai_release = _missing_prefect
    build_evidence_release = _missing_prefect
    generate_llm_batch = _missing_prefect
    build_claim_measurement_release = _missing_prefect
    build_analytical_release = _missing_prefect
    build_visualization_release = _missing_prefect
    certify_dashboard_release = _missing_prefect
    build_complete_release_bundle = _missing_prefect
    prefect_acceptance_fixture = _missing_prefect
    prefect_approval_acceptance_fixture = _missing_prefect
    promote_research_release = _missing_prefect
    promote_model_version = _missing_prefect
else:
    def _flow(name: str):
        return flow(name=name, persist_result=True, log_prints=True)

    @_flow("verify-source-environment")
    def verify_source_environment(
        input_artifact_ids: dict[str, str] | None = None,
        parameters: dict[str, Any] | None = None,
        requested_by: str = "prefect-user",
    ) -> dict[str, Any]:
        return _execute("verify_source_environment", input_artifact_ids, parameters, requested_by)

    @_flow("train-model-release")
    def train_model_release(input_artifact_ids=None, parameters=None, requested_by="prefect-user"):
        return _execute("train_model_release", input_artifact_ids, parameters, requested_by)

    @_flow("register-verified-training-release")
    def register_verified_training_release(input_artifact_ids=None, parameters=None, requested_by="prefect-user"):
        return _execute("register_verified_training_release", input_artifact_ids, parameters, requested_by)

    @_flow("build-xai-release")
    def build_xai_release(input_artifact_ids=None, parameters=None, requested_by="prefect-user"):
        return _execute("build_xai_release", input_artifact_ids, parameters, requested_by)

    @_flow("build-evidence-release")
    def build_evidence_release(input_artifact_ids=None, parameters=None, requested_by="prefect-user"):
        return _execute("build_evidence_release", input_artifact_ids, parameters, requested_by)

    @_flow("generate-llm-batch")
    def generate_llm_batch(input_artifact_ids=None, parameters=None, requested_by="prefect-user"):
        return _execute("generate_llm_batch", input_artifact_ids, parameters, requested_by)

    @_flow("build-claim-measurement-release")
    def build_claim_measurement_release(input_artifact_ids=None, parameters=None, requested_by="prefect-user"):
        return _execute("build_claim_measurement_release", input_artifact_ids, parameters, requested_by)

    @_flow("build-analytical-release")
    def build_analytical_release(input_artifact_ids=None, parameters=None, requested_by="prefect-user"):
        return _execute("build_analytical_release", input_artifact_ids, parameters, requested_by)

    @_flow("build-visualization-release")
    def build_visualization_release(input_artifact_ids=None, parameters=None, requested_by="prefect-user"):
        return _execute("build_visualization_release", input_artifact_ids, parameters, requested_by)

    @_flow("certify-dashboard-release")
    def certify_dashboard_release(input_artifact_ids=None, parameters=None, requested_by="prefect-user"):
        return _execute("certify_dashboard_release", input_artifact_ids, parameters, requested_by)

    @_flow("build-complete-release-bundle")
    def build_complete_release_bundle(input_artifact_ids=None, parameters=None, requested_by="prefect-user"):
        return _execute("build_complete_release_bundle", input_artifact_ids, parameters, requested_by)

    @_flow("prefect-acceptance-fixture")
    def prefect_acceptance_fixture(input_artifact_ids=None, parameters=None, requested_by="phase6-acceptance"):
        return _execute("prefect_acceptance_fixture", input_artifact_ids, parameters, requested_by)

    @_flow("prefect-approval-acceptance-fixture")
    def prefect_approval_acceptance_fixture(input_artifact_ids=None, parameters=None, requested_by="phase6-acceptance"):
        return _execute("prefect_approval_acceptance_fixture", input_artifact_ids, parameters, requested_by)

    @_flow("promote-research-release")
    def promote_research_release(input_artifact_ids=None, parameters=None, requested_by="researchops-api"):
        return _execute("promote_research_release", input_artifact_ids, parameters, requested_by)

    @_flow("promote-model-version")
    def promote_model_version(input_artifact_ids=None, parameters=None, requested_by="researchops-api"):
        return _execute("promote_model_version", input_artifact_ids, parameters, requested_by)
