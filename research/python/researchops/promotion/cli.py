from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from research.python.researchops.mlflow_tracking.registry_gateway import RealRegistryGateway
from research.python.researchops.mlflow_tracking.reporting import emit_json_report
from research.python.researchops.mlflow_tracking.settings import MLflowSettings
from research.python.researchops.ops_core.db.engine import create_engine_from_settings
from research.python.researchops.ops_core.repositories.sqlalchemy import SqlAlchemyOpsRepository
from research.python.researchops.ops_core.settings import DatabaseSettings

from .contracts import load_promotion_policies, promotion_policy_sha256
from .service import ModelPromotionService, ReleasePromotionService, WaiverService


def _add_report_path(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--report-path")


def _instant(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="researchops-promotion")
    sub = parser.add_subparsers(dest="command", required=True)

    policy = sub.add_parser("validate-policies")
    _add_report_path(policy)

    inspect = sub.add_parser("inspect-policy")
    inspect.add_argument("--target-type", required=True, choices=("release", "model_version"))
    inspect.add_argument("--target-kind", required=True)
    _add_report_path(inspect)

    waiver = sub.add_parser("grant-waiver")
    waiver.add_argument("--gate-id", required=True)
    waiver.add_argument("--scope-type", required=True, choices=("release",))
    waiver.add_argument("--scope-id", required=True)
    waiver.add_argument("--target-kind", required=True)
    waiver.add_argument("--policy-id", required=True)
    waiver.add_argument("--approval-id", required=True)
    waiver.add_argument("--requested-by", required=True)
    waiver.add_argument("--decided-by", required=True)
    waiver.add_argument("--reason", required=True)
    waiver.add_argument("--expires-at", required=True, type=_instant)
    waiver.add_argument("--request-key")
    _add_report_path(waiver)

    revoke = sub.add_parser("revoke-waiver")
    revoke.add_argument("--waiver-id", required=True)
    revoke.add_argument("--actor", required=True)
    revoke.add_argument("--reason", required=True)
    _add_report_path(revoke)

    release = sub.add_parser("promote-release")
    release.add_argument("--release-id", required=True)
    release.add_argument("--approval-id", required=True)
    release.add_argument("--actor", required=True)
    release.add_argument("--reason", required=True)
    release.add_argument("--idempotency-key", required=True)
    release.add_argument("--expected-status")
    release.add_argument("--target-status")
    _add_report_path(release)

    model = sub.add_parser("promote-model")
    model.add_argument("--model-name", required=True)
    model.add_argument("--version", required=True)
    model.add_argument("--approval-id", required=True)
    model.add_argument("--actor", required=True)
    model.add_argument("--reason", required=True)
    model.add_argument("--idempotency-key", required=True)
    model.add_argument("--request-id")
    _add_report_path(model)
    return parser


def _decision_payload(item) -> dict[str, Any]:
    return {
        "decision_id": item.id,
        "idempotency_key": item.idempotency_key,
        "target_type": item.target_type,
        "target_id": item.target_id,
        "target_kind": item.target_kind,
        "policy_id": item.policy_id,
        "policy_version": item.policy_version,
        "policy_sha256": item.policy_sha256,
        "expected_state": item.expected_state,
        "target_state": item.target_state,
        "decision": item.decision,
        "execution_status": item.execution_status,
        "gate_snapshot": item.gate_snapshot,
        "approval_snapshot": item.approval_snapshot,
        "waiver_snapshot": item.waiver_snapshot,
        "previous_external_state": item.previous_external_state,
        "new_external_state": item.new_external_state,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report_path = getattr(args, "report_path", None)
    catalog = load_promotion_policies()

    if args.command == "validate-policies":
        payload = {
            "schema_version": "promotion_policy_validation_v1",
            "passed": True,
            "policy_count": len(catalog.policies),
            "policy_sha256": promotion_policy_sha256(),
            "policy_ids": sorted(item.policy_id for item in catalog.policies),
        }
        emit_json_report(payload, report_path=report_path)
        return 0

    if args.command == "inspect-policy":
        policy = catalog.for_target(args.target_type, args.target_kind)
        payload = {
            "schema_version": "promotion_policy_inspection_v1",
            "policy_sha256": promotion_policy_sha256(),
            "policy": policy.model_dump(mode="json"),
        }
        emit_json_report(payload, report_path=report_path)
        return 0

    settings = DatabaseSettings.from_environment()
    assert settings is not None
    engine = create_engine_from_settings(settings)
    with Session(engine) as session, session.begin():
        repository = SqlAlchemyOpsRepository(session)
        if args.command == "grant-waiver":
            item = WaiverService(repository).grant(
                gate_id=args.gate_id,
                scope_type=args.scope_type,
                scope_id=args.scope_id,
                target_kind=args.target_kind,
                policy_id=args.policy_id,
                approval_id=args.approval_id,
                requested_by=args.requested_by,
                decided_by=args.decided_by,
                reason=args.reason,
                expires_at=args.expires_at,
                request_key=args.request_key,
            )
            payload = {
                "schema_version": "gate_waiver_result_v1",
                "waiver_id": item.id,
                "gate_result_id": item.gate_result_id,
                "evaluation_id": item.evaluation_id,
                "status": item.status,
                "expires_at": item.expires_at.isoformat(),
            }
        elif args.command == "revoke-waiver":
            item = WaiverService(repository).revoke(
                args.waiver_id,
                actor=args.actor,
                reason=args.reason,
            )
            payload = {
                "schema_version": "gate_waiver_result_v1",
                "waiver_id": item.id,
                "status": item.status,
                "revoked_at": item.revoked_at.isoformat() if item.revoked_at else None,
            }
        elif args.command == "promote-release":
            decision = ReleasePromotionService(repository).promote(
                args.release_id,
                approval_id=args.approval_id,
                actor=args.actor,
                reason=args.reason,
                idempotency_key=args.idempotency_key,
                expected_status=args.expected_status,
                target_status=args.target_status,
            )
            payload = {"schema_version": "promotion_decision_result_v1", **_decision_payload(decision)}
        else:
            mlflow = MLflowSettings.from_environment()
            decision = ModelPromotionService(
                repository,
                RealRegistryGateway(mlflow.tracking_uri),
            ).promote(
                model_name=args.model_name,
                version=args.version,
                approval_id=args.approval_id,
                actor=args.actor,
                reason=args.reason,
                idempotency_key=args.idempotency_key,
                request_id=args.request_id,
            )
            payload = {"schema_version": "promotion_decision_result_v1", **_decision_payload(decision)}
        emit_json_report(payload, report_path=report_path)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
