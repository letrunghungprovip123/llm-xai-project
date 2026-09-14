from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from research.python.researchops.contracts.io import project_root
from research.python.researchops.orchestration.environment import (
    dependency_lock_sha256,
)
from research.python.researchops.orchestration.reporting import write_json_report


def _env_json(name: str, default: Any) -> Any:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {name}") from exc


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} is required")
    return value.strip()


def _stage_report_path(run_dir: Path) -> Path:
    raw = _required_env("RESEARCHOPS_REPORT_PATH")
    path = Path(raw).resolve()
    expected = (run_dir / "stage-report.json").resolve()
    if path != expected:
        raise RuntimeError(
            "RESEARCHOPS_REPORT_PATH must point to the canonical stage report"
        )
    return path


def _require_registration_result(
    payload: Any,
    *,
    source_artifact_id: str,
    source_manifest_sha256: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("MLflow registration result must be a JSON object")
    if payload.get("schema_version") != "mlflow_training_registration_result_v1":
        raise RuntimeError("Unexpected MLflow registration result schema")
    receipt_artifact_id = payload.get("receipt_artifact_id")
    receipt_manifest_sha256 = payload.get("receipt_manifest_sha256")
    if not isinstance(receipt_artifact_id, str) or not receipt_artifact_id.startswith(
        "artifact_mlflow_registration_receipt_"
    ):
        raise RuntimeError("MLflow registration result has no canonical receipt artifact")
    if (
        not isinstance(receipt_manifest_sha256, str)
        or len(receipt_manifest_sha256) != 64
        or any(character not in "0123456789abcdef" for character in receipt_manifest_sha256)
    ):
        raise RuntimeError("MLflow registration result has an invalid receipt manifest hash")
    for section_name in ("tracking", "registry"):
        section = payload.get(section_name)
        if not isinstance(section, dict):
            raise RuntimeError(f"MLflow registration result is missing {section_name}")
        if section.get("source_artifact_id") != source_artifact_id:
            raise RuntimeError(
                f"MLflow {section_name} source artifact does not match the stage input"
            )
        if section.get("source_manifest_sha256") != source_manifest_sha256:
            raise RuntimeError(
                f"MLflow {section_name} source manifest does not match the stage input"
            )
    return payload


def _run_dir() -> Path:
    raw = os.getenv("RESEARCHOPS_RUN_DIR")
    if not raw:
        raise RuntimeError("RESEARCHOPS_RUN_DIR is required")
    path = Path(raw).resolve()
    root = project_root().resolve()
    if path != root and root not in path.parents:
        raise RuntimeError("RESEARCHOPS_RUN_DIR escapes project root")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _git(args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=project_root(),
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


def verify_environment() -> dict[str, Any]:
    root = project_root().resolve()
    commit = _git(["rev-parse", "HEAD"]) or "0" * 40
    dirty = bool(_git(["status", "--porcelain"]))
    report = {
        "schema_version": "environment_verification_report_v1",
        "passed": True,
        "source_commit": commit,
        "git_dirty": dirty,
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "operating_system": platform.platform(),
        "architecture": platform.machine(),
        "dependency_lock_sha256": dependency_lock_sha256(root),
        "stage_registry_exists": (root / "config/platform/stages.yaml").is_file(),
        "flow_catalog_exists": (root / "config/platform/flows.yaml").is_file(),
        "artifact_manifest_schema_exists": (
            root / "config/platform/artifact_manifest_schema_v3.json"
        ).is_file(),
    }
    report["passed"] = all(
        report[key]
        for key in (
            "stage_registry_exists",
            "flow_catalog_exists",
            "artifact_manifest_schema_exists",
        )
    )
    target = _run_dir() / "environment_verification_report.json"
    write_json_report(target, report)
    return report


def build_complete_bundle() -> dict[str, Any]:
    artifact_ids = _env_json("RESEARCHOPS_INPUT_ARTIFACT_IDS", {})
    if not isinstance(artifact_ids, dict) or not artifact_ids:
        raise RuntimeError("Complete release bundle requires input artifacts")
    report = {
        "schema_version": "complete_release_bundle_v1",
        "pipeline_run_id": os.environ["RESEARCHOPS_PIPELINE_RUN_ID"],
        "stage_run_id": os.environ["RESEARCHOPS_STAGE_RUN_ID"],
        "inputs": dict(sorted(artifact_ids.items())),
        "input_count": len(artifact_ids),
        "bundle_identity_sha256": hashlib.sha256(
            json.dumps(
                artifact_ids,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "promotion_performed": False,
        "note": (
            "This immutable bundle indexes verified parent artifacts; it does "
            "not copy or mutate scientific bytes and does not promote releases."
        ),
    }
    write_json_report(_run_dir() / "complete_release_bundle.json", report)
    return report


def mlflow_register() -> dict[str, Any]:
    run_dir = _run_dir()
    source_artifact_id = _required_env(
        "RESEARCHOPS_INPUT_TRAINED_MODELS_ARTIFACT_ID"
    )
    source_manifest_sha256 = _required_env(
        "RESEARCHOPS_INPUT_TRAINED_MODELS_MANIFEST_SHA256"
    )
    source_contract = _required_env(
        "RESEARCHOPS_INPUT_TRAINED_MODELS_CONTRACT"
    )
    if source_contract != "trained_model":
        raise RuntimeError(
            "MLflow registration requires the trained_model input contract"
        )
    artifact_profile = _env_json(
        "RESEARCHOPS_PARAMETER_ARTIFACT_PROFILE",
        os.getenv("RESEARCHOPS_ARTIFACT_PROFILE", "development-minio"),
    )
    if not isinstance(artifact_profile, str) or not artifact_profile.strip():
        raise RuntimeError("artifact_profile must be a non-empty string")

    registration_path = run_dir / "mlflow-training-registration-result.json"
    from research.python.researchops.mlflow_tracking.cli import main as mlflow_main

    exit_code = mlflow_main(
        [
            "register-training-release",
            "--artifact-profile",
            artifact_profile,
            "--artifact-id",
            source_artifact_id,
            "--report-path",
            str(registration_path),
        ]
    )
    if exit_code not in (None, 0):
        raise SystemExit(int(exit_code))
    try:
        registration = json.loads(registration_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "MLflow registration did not produce a valid canonical result"
        ) from exc
    registration = _require_registration_result(
        registration,
        source_artifact_id=source_artifact_id,
        source_manifest_sha256=source_manifest_sha256,
    )
    tracking = registration["tracking"]
    registry = registration["registry"]
    report = {
        "schema_version": "stage_command_result_v1",
        "outputs": {
            "receipt": {
                "artifact_id": registration["receipt_artifact_id"],
                "artifact_type": "mlflow_registration_receipt",
                "manifest_sha256": registration["receipt_manifest_sha256"],
                "source_inputs": ["trained_models"],
            }
        },
        "metadata": {
            "adapter": "phase5_mlflow_registration_v1",
            "source_artifact_id": source_artifact_id,
            "source_manifest_sha256": source_manifest_sha256,
            "receipt_reused": bool(registration.get("receipt_reused", False)),
            "parent_run_id": tracking.get("parent_run_id"),
            "candidate_version": registry.get("candidate_version"),
            "registered_model_name": registry.get("registered_model_name"),
        },
    }
    write_json_report(_stage_report_path(run_dir), report)
    return report


def acceptance_fixture(*, protected: bool = False) -> dict[str, Any]:
    simulation = _env_json("RESEARCHOPS_PARAMETER_SIMULATION", "normal")
    sleep_seconds = float(
        _env_json("RESEARCHOPS_PARAMETER_SLEEP_SECONDS", 30)
    )
    pipeline_id = os.environ["RESEARCHOPS_PIPELINE_RUN_ID"]
    pipeline_root = _run_dir().parent
    if simulation == "transient-once":
        marker = pipeline_root / ".transient-once-completed"
        if not marker.exists():
            marker.write_text("first attempt failed\n", encoding="utf-8")
            print("Simulated transient infrastructure failure", file=sys.stderr)
            raise SystemExit(75)
    elif simulation == "rate-limit-once":
        marker = pipeline_root / ".rate-limit-once-completed"
        if not marker.exists():
            marker.write_text("first attempt rate-limited\n", encoding="utf-8")
            print("Simulated provider rate limit", file=sys.stderr)
            raise SystemExit(77)
    elif simulation == "contract-failure":
        # Exit successfully without the declared output. The execution adapter
        # must fail closed during output discovery and must not retry.
        return {
            "schema_version": "orchestration_acceptance_result_v1",
            "simulation": simulation,
            "output_written": False,
        }
    elif simulation == "sleep":
        time.sleep(max(0.0, min(sleep_seconds, 600.0)))
    elif simulation != "normal":
        raise ValueError(f"Unknown acceptance simulation: {simulation!r}")

    report = {
        "schema_version": (
            "orchestration_approval_acceptance_result_v1"
            if protected
            else "orchestration_acceptance_result_v1"
        ),
        "pipeline_run_id": pipeline_id,
        "stage_run_id": os.environ["RESEARCHOPS_STAGE_RUN_ID"],
        "simulation": simulation,
        "protected": protected,
        "output_written": True,
    }
    filename = (
        "orchestration_approval_acceptance_result.json"
        if protected
        else "orchestration_acceptance_result.json"
    )
    write_json_report(_run_dir() / filename, report)
    return report



def _promotion_parameter(name: str) -> Any:
    return _env_json(f"RESEARCHOPS_PARAMETER_{name.upper()}", None)


def _promotion_session():
    from research.python.researchops.ops_core.db import create_engine_from_settings, create_session_factory
    from research.python.researchops.ops_core.settings import DatabaseSettings

    settings = DatabaseSettings.from_environment()
    if settings is None:
        raise RuntimeError("RESEARCHOPS_DATABASE_URL is required for promotion")
    return create_session_factory(create_engine_from_settings(settings))()


def release_promote() -> dict[str, Any]:
    from research.python.researchops.ops_core.repositories.sqlalchemy import SqlAlchemyOpsRepository
    from research.python.researchops.promotion import ReleasePromotionService, promotion_policy_sha256

    release_id = str(_promotion_parameter("release_id") or "")
    approval_id = str(_promotion_parameter("approval_id") or "")
    actor = str(_promotion_parameter("actor") or "prefect-worker")
    reason = str(_promotion_parameter("reason") or "")
    idempotency_key = str(_promotion_parameter("idempotency_key") or "")
    expected_status = str(_promotion_parameter("expected_status") or "")
    target_status = str(_promotion_parameter("target_status") or "")
    expected_policy_sha = str(_promotion_parameter("policy_sha256") or "")
    observed_policy_sha = promotion_policy_sha256()
    if expected_policy_sha != observed_policy_sha:
        raise RuntimeError("Promotion policy hash changed before release promotion")
    if not all((release_id, approval_id, reason, idempotency_key, expected_status, target_status)):
        raise RuntimeError("Release promotion parameters are incomplete")
    session = _promotion_session()
    try:
        repository = SqlAlchemyOpsRepository(session)
        decision = ReleasePromotionService(repository).promote(
            release_id, approval_id=approval_id, actor=actor, reason=reason,
            idempotency_key=idempotency_key, expected_status=expected_status,
            target_status=target_status,
        )
        session.commit()
        report = {
            "schema_version": "release_promotion_receipt_v1",
            "passed": decision.execution_status == "COMPLETED",
            "status": decision.execution_status,
            "checks": {
                "decision_approved": {"passed": decision.decision == "APPROVED", "expected": "APPROVED", "observed": decision.decision},
                "execution_completed": {"passed": decision.execution_status == "COMPLETED", "expected": "COMPLETED", "observed": decision.execution_status},
            },
            "decision_id": decision.id,
            "release_id": release_id,
            "policy_id": decision.policy_id,
            "policy_version": decision.policy_version,
            "policy_sha256": decision.policy_sha256,
            "target_state": decision.target_state,
            "limitations": [],
        }
        write_json_report(_run_dir() / "release_promotion_receipt.json", report)
        return report
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def model_promote() -> dict[str, Any]:
    from research.python.researchops.mlflow_tracking.registry_gateway import RealRegistryGateway
    from research.python.researchops.ops_core.repositories.sqlalchemy import SqlAlchemyOpsRepository
    from research.python.researchops.promotion import ModelPromotionService, promotion_policy_sha256

    model_name = str(_promotion_parameter("model_name") or "")
    version = str(_promotion_parameter("version") or "")
    approval_id = str(_promotion_parameter("approval_id") or "")
    actor = str(_promotion_parameter("actor") or "prefect-worker")
    reason = str(_promotion_parameter("reason") or "")
    idempotency_key = str(_promotion_parameter("idempotency_key") or "")
    request_id = str(_promotion_parameter("request_id") or "") or None
    expected_policy_sha = str(_promotion_parameter("policy_sha256") or "")
    observed_policy_sha = promotion_policy_sha256()
    if expected_policy_sha != observed_policy_sha:
        raise RuntimeError("Promotion policy hash changed before model promotion")
    if not all((model_name, version, approval_id, reason, idempotency_key)):
        raise RuntimeError("Model promotion parameters are incomplete")
    tracking_uri = os.getenv("MLFLOW_INTERNAL_TRACKING_URI") or os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        raise RuntimeError("MLFLOW_TRACKING_URI is required for model promotion")
    session = _promotion_session()
    try:
        repository = SqlAlchemyOpsRepository(session)
        decision = ModelPromotionService(repository, RealRegistryGateway(tracking_uri)).promote(
            model_name=model_name, version=version, approval_id=approval_id,
            actor=actor, reason=reason, idempotency_key=idempotency_key,
            request_id=request_id,
        )
        session.commit()
        report = {
            "schema_version": "model_promotion_receipt_v1",
            "passed": decision.execution_status == "COMPLETED",
            "status": decision.execution_status,
            "checks": {
                "decision_approved": {"passed": decision.decision == "APPROVED", "expected": "APPROVED", "observed": decision.decision},
                "execution_completed": {"passed": decision.execution_status == "COMPLETED", "expected": "COMPLETED", "observed": decision.execution_status},
            },
            "decision_id": decision.id,
            "model_name": model_name,
            "version": version,
            "policy_id": decision.policy_id,
            "policy_version": decision.policy_version,
            "policy_sha256": decision.policy_sha256,
            "new_external_state": decision.new_external_state,
            "limitations": [],
        }
        write_json_report(_run_dir() / "model_promotion_receipt.json", report)
        return report
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="researchops-stage-command")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify-environment")
    sub.add_parser("build-complete-bundle")
    sub.add_parser("mlflow-register")
    sub.add_parser("acceptance-fixture")
    sub.add_parser("approval-acceptance-fixture")
    sub.add_parser("release-promote")
    sub.add_parser("model-promote")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "verify-environment":
        report = verify_environment()
    elif args.command == "build-complete-bundle":
        report = build_complete_bundle()
    elif args.command == "mlflow-register":
        report = mlflow_register()
    elif args.command == "acceptance-fixture":
        report = acceptance_fixture()
    elif args.command == "approval-acceptance-fixture":
        report = acceptance_fixture(protected=True)
    elif args.command == "release-promote":
        report = release_promote()
    elif args.command == "model-promote":
        report = model_promote()
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
