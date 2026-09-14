from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from research.python.researchops.artifacts.profiles import load_store
from research.python.researchops.ops_core.db.engine import create_engine_from_settings
from research.python.researchops.ops_core.repositories.sqlalchemy import SqlAlchemyOpsRepository
from research.python.researchops.ops_core.services.artifact_registration import ArtifactRegistrationService
from research.python.researchops.ops_core.settings import DatabaseSettings

from .bootstrap import bootstrap_experiments
from .client import RealMLflowGateway
from .contracts import (
    load_experiment_catalog,
    load_registry_policy,
    load_tracking_contract,
    validate_contract_set,
)
from .package_training import build_training_release_package
from .settings import MLflowSettings, write_local_environment
from .smoke import run_live_smoke
from .tracking import track_training_release
from .tracking_gateway import RealTrackingGateway
from .registry import register_training_models
from .registry_gateway import RealRegistryGateway
from .receipts import build_receipt, publish_receipt
from .promotion import promote_candidate
from .reconciliation import reconcile_mlflow
from research.python.researchops.gates.contracts import (
    GateAdapterIdentity,
    GateCheck,
    GateEvaluationDraft,
    GateEvidence,
    GatePolicyIdentity,
    GateScope,
    GateSource,
)
from research.python.researchops.gates.service import GateEvaluationService
from research.python.researchops.ops_core.services.audit import record_audit
from .training_release import download_training_release, verify_training_release_portability
from .reporting import emit_json_report


def _add_report_path(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--report-path",
        help="Write the canonical machine-readable JSON result atomically.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="researchops-mlflow")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate-contracts", "check-config", "health", "bootstrap-experiments", "smoke-test"):
        command_parser = sub.add_parser(name)
        _add_report_path(command_parser)
    init = sub.add_parser("init-local-env")
    init.add_argument("--output", default=".env.researchops-mlflow.local")
    init.add_argument("--force", action="store_true")

    package = sub.add_parser("package-training-release")
    package.add_argument("--artifact-profile", default="development-minio")
    package.add_argument("--dataset-release-id", default="UNREGISTERED_LEGACY")
    package.add_argument("--feature-matrix-artifact-id", default="UNREGISTERED_LEGACY")
    package.add_argument("--split-artifact-id", default="UNREGISTERED_LEGACY")
    package.add_argument("--preprocessor-artifact-id", default="UNREGISTERED_LEGACY")
    package.add_argument("--environment-snapshot-id")
    package.add_argument(
        "--model-source-dir",
        help=(
            "Directory containing the three joblib bundles. Defaults to "
            "<project>/artifacts/models. External directories are an explicit "
            "one-time import and are never inferred from legacy registry paths."
        ),
    )
    package.add_argument("--skip-db-registration", action="store_true")
    _add_report_path(package)

    inspect = sub.add_parser("inspect-training-release")
    inspect.add_argument("--artifact-id", required=True)
    inspect.add_argument("--artifact-profile", default="development-minio")
    _add_report_path(inspect)

    track = sub.add_parser("track-training-release")
    track.add_argument("--artifact-id", required=True)
    track.add_argument("--artifact-profile", default="development-minio")
    _add_report_path(track)

    register = sub.add_parser("register-training-release")
    register.add_argument("--artifact-id", required=True)
    register.add_argument("--artifact-profile", default="development-minio")
    _add_report_path(register)

    promote = sub.add_parser("promote")
    promote.add_argument("--version", required=True)
    promote.add_argument("--approval-id", required=True)
    promote.add_argument("--actor", required=True)
    promote.add_argument("--request-id")
    _add_report_path(promote)

    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--artifact-profile", default="development-minio")
    reconcile.add_argument("--mode", choices=("report-only",), default="report-only")
    _add_report_path(reconcile)

    portability = sub.add_parser("verify-training-release-portability")
    portability.add_argument("--artifact-id", required=True)
    portability.add_argument("--artifact-profile", default="development-minio")
    _add_report_path(portability)
    return parser


def _register_artifact(store, artifact_id: str) -> bool:
    settings = DatabaseSettings.from_environment()
    assert settings is not None
    engine = create_engine_from_settings(settings)
    with Session(engine) as session, session.begin():
        repository = SqlAlchemyOpsRepository(session)
        result = ArtifactRegistrationService(repository, store).register(
            artifact_id, actor="researchops-mlflow", request_id="package-training-release"
        )
        return result.created



def _repository_session():
    settings = DatabaseSettings.from_environment()
    assert settings is not None
    engine = create_engine_from_settings(settings)
    return Session(engine)


def _register_training_release(args, settings: MLflowSettings) -> dict[str, object]:
    store = load_store(args.artifact_profile)
    source_manifest = store.get_manifest(args.artifact_id)
    tracking = track_training_release(
        store=store,
        artifact_id=args.artifact_id,
        gateway=RealTrackingGateway(settings.tracking_uri),
        contract=load_tracking_contract(),
    )
    registry_gateway = RealRegistryGateway(settings.tracking_uri)
    registration = register_training_models(
        tracking=tracking,
        source_manifest=source_manifest,
        gateway=registry_gateway,
        policy=load_registry_policy(),
    )
    receipt = build_receipt(
        tracking=tracking,
        registration=registration,
        mlflow_version=settings.expected_version,
    )
    receipt_reference, receipt_reused = publish_receipt(
        store=store,
        source_artifact_id=args.artifact_id,
        receipt=receipt,
    )

    with _repository_session() as session, session.begin():
        repository = SqlAlchemyOpsRepository(session)
        registration_service = ArtifactRegistrationService(repository, store)
        registration_service.register(
            args.artifact_id,
            actor="researchops-mlflow",
            request_id="mlflow-register-source",
        )
        receipt_registration = registration_service.register(
            receipt_reference.artifact_id,
            actor="researchops-mlflow",
            request_id="mlflow-register-receipt",
        )
        target_id = (
            f"{registration.registered_model_name}:"
            f"{registration.candidate.version}"
        )
        record_audit(
            repository,
            actor="researchops-mlflow",
            action="mlflow.model_versions_registered",
            target_type="model",
            target_id=registration.registered_model_name,
            after_state=registration.to_dict(),
            request_id="mlflow-register-training-release",
        )
        record_audit(
            repository,
            actor="researchops-mlflow",
            action="mlflow.candidate_assigned",
            target_type="model_version",
            target_id=target_id,
            after_state={"alias": "candidate"},
            request_id="mlflow-register-training-release",
        )
        record_audit(
            repository,
            actor="researchops-mlflow",
            action="mlflow.receipt_published",
            target_type="artifact",
            target_id=receipt_reference.artifact_id,
            after_state={
                "manifest_sha256": receipt_reference.manifest_sha256,
                "reused": receipt_reused,
            },
            request_id="mlflow-register-training-release",
        )
        gate_service = GateEvaluationService(repository)
        receipt_check = GateCheck(
            check_id="mlflow.registration_receipt",
            passed=True,
            expected={"receipt_required": True, "candidate_alias_required": True},
            observed={
                "receipt_artifact_id": receipt_reference.artifact_id,
                "candidate_version": registration.candidate.version,
            },
        )
        receipt_source = GateSource(
            artifact_id=receipt_reference.artifact_id,
            manifest_sha256=receipt_reference.manifest_sha256,
            contract="mlflow_registration_receipt",
        )
        receipt_evidence = GateEvidence(
            artifact_id=receipt_reference.artifact_id,
            manifest_sha256=receipt_reference.manifest_sha256,
        )
        artifact_gate = gate_service.record(
            GateEvaluationDraft(
                gate_id="MLFLOW_MODEL_REGISTERED",
                scope=GateScope(type="artifact", id=receipt_reference.artifact_id),
                outcome="PASSED",
                adapter=GateAdapterIdentity(
                    id="mlflow_registration_receipt_v1", version=1
                ),
                policy=GatePolicyIdentity(id="scientific_quality", version="1"),
                source=receipt_source,
                evidence=receipt_evidence,
                expected={"receipt_required": True, "candidate_alias_required": True},
                observed={
                    "registered_model_name": registration.registered_model_name,
                    "candidate_version": registration.candidate.version,
                },
                checks=(receipt_check,),
                source_contracts=(
                    "mlflow_registration_receipt_v1",
                    "mlflow_registry_policy_v1",
                ),
                evaluated_at=datetime.now(timezone.utc),
            ),
            actor="researchops-mlflow",
        )
        gate_service.record(
            GateEvaluationDraft(
                gate_id="MLFLOW_MODEL_REGISTERED",
                scope=GateScope(type="model_version", id=target_id),
                outcome="PASSED",
                adapter=GateAdapterIdentity(
                    id="artifact_to_model_version_projection_v1", version=1
                ),
                policy=GatePolicyIdentity(id="scope_projection", version="1"),
                source=receipt_source,
                evidence=receipt_evidence,
                expected={"receipt_required": True, "candidate_alias_required": True},
                observed={
                    "registered_model_name": registration.registered_model_name,
                    "candidate_version": registration.candidate.version,
                },
                checks=(receipt_check,),
                source_contracts=(
                    "mlflow_registration_receipt_v1",
                    "mlflow_registry_policy_v1",
                ),
                source_evaluation_ids=(artifact_gate.evaluation.id,),
                evaluated_at=datetime.now(timezone.utc),
            ),
            actor="researchops-mlflow",
        )
        for item in registration.versions:
            registry_gateway.set_run_tags(
                item.run_id,
                {
                    "researchops.receipt_artifact_id": receipt_reference.artifact_id,
                    "researchops.integration_state": "COMPLETE",
                },
            )
        registry_gateway.set_run_tags(
            tracking.parent_run_id,
            {
                "researchops.receipt_artifact_id": receipt_reference.artifact_id,
                "researchops.integration_state": "COMPLETE",
            },
        )
        repository.flush()
    return {
        "schema_version": "mlflow_training_registration_result_v1",
        "tracking": tracking.to_dict(),
        "registry": registration.to_dict(),
        "receipt_artifact_id": receipt_reference.artifact_id,
        "receipt_manifest_sha256": receipt_reference.manifest_sha256,
        "receipt_manifest_uri": receipt_reference.uri,
        "receipt_database_registration_created": receipt_registration.created,
        "receipt_reused": receipt_reused,
    }

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report_path = getattr(args, "report_path", None)

    if args.command == "validate-contracts":
        payload = validate_contract_set()
        emit_json_report(payload, report_path=report_path)
        return 0
    if args.command == "init-local-env":
        target = write_local_environment(Path(args.output), overwrite=args.force)
        emit_json_report({"created": str(target), "mode": oct(target.stat().st_mode & 0o777)})
        return 0
    if args.command == "package-training-release":
        with build_training_release_package(
            dataset_release_id=args.dataset_release_id,
            feature_matrix_artifact_id=args.feature_matrix_artifact_id,
            split_artifact_id=args.split_artifact_id,
            preprocessor_artifact_id=args.preprocessor_artifact_id,
            environment_snapshot_id=args.environment_snapshot_id,
            model_source_dir=(
                Path(args.model_source_dir) if args.model_source_dir else None
            ),
        ) as build:
            store = load_store(args.artifact_profile)
            reference = store.put_package(build.package)
            created = (
                False
                if args.skip_db_registration
                else _register_artifact(store, reference.artifact_id)
            )
            payload = {
                "schema_version": "model_training_release_package_result_v1",
                "artifact_id": reference.artifact_id,
                "manifest_sha256": reference.manifest_sha256,
                "manifest_uri": reference.uri,
                "database_registration_created": created,
                "limitations": list(build.package.manifest.limitations),
                "portable": True,
            }
            emit_json_report(payload, report_path=report_path)
        return 0
    if args.command == "inspect-training-release":
        import tempfile

        store = load_store(args.artifact_profile)
        with tempfile.TemporaryDirectory(prefix="researchops-inspect-model-") as directory:
            release = download_training_release(store, args.artifact_id, Path(directory))
            payload = {
                "artifact_id": release.manifest.artifact_id,
                "manifest_sha256": release.manifest.manifest_sha256,
                "models": [item.model_dump(mode="json") for item in release.registry.models],
                "selected_model": release.registry.best_model["model_name"],
            }
            emit_json_report(payload, report_path=report_path)
        return 0
    if args.command == "verify-training-release-portability":
        payload = verify_training_release_portability(
            load_store(args.artifact_profile), args.artifact_id
        )
        emit_json_report(payload, report_path=report_path)
        return 0 if payload["passed"] else 1

    settings = MLflowSettings.from_environment()
    if args.command == "check-config":
        emit_json_report(settings.redacted_dict(), report_path=report_path)
        return 0
    gateway = RealMLflowGateway(settings)
    if args.command == "health":
        report = gateway.version_report()
        emit_json_report(report.to_dict(), report_path=report_path)
        return 0 if report.passed else 1
    if args.command == "bootstrap-experiments":
        results = bootstrap_experiments(gateway, load_experiment_catalog())
        payload = {
            "schema_version": "mlflow_experiment_bootstrap_v1",
            "passed": True,
            "experiments": [result.__dict__ for result in results],
        }
        emit_json_report(payload, report_path=report_path)
        return 0
    if args.command == "smoke-test":
        emit_json_report(run_live_smoke(settings), report_path=report_path)
        return 0
    if args.command == "track-training-release":
        result = track_training_release(
            store=load_store(args.artifact_profile),
            artifact_id=args.artifact_id,
            gateway=RealTrackingGateway(settings.tracking_uri),
            contract=load_tracking_contract(),
        )
        emit_json_report(result.to_dict(), report_path=report_path)
        return 0
    if args.command == "register-training-release":
        emit_json_report(
            _register_training_release(args, settings),
            report_path=report_path,
        )
        return 0
    if args.command == "promote":
        with _repository_session() as session, session.begin():
            result = promote_candidate(
                version=args.version,
                approval_id=args.approval_id,
                actor=args.actor,
                request_id=args.request_id,
                gateway=RealRegistryGateway(settings.tracking_uri),
                repository=SqlAlchemyOpsRepository(session),
                policy=load_registry_policy(),
            )
        emit_json_report(result.__dict__, report_path=report_path)
        return 0
    if args.command == "reconcile":
        report = reconcile_mlflow(
            store=load_store(args.artifact_profile),
            gateway=RealRegistryGateway(settings.tracking_uri),
            policy=load_registry_policy(),
        )
        emit_json_report(report.to_dict(), report_path=report_path)
        return 0 if report.passed else 1
    raise AssertionError(args.command)
