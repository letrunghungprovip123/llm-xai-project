from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID

from research.python.researchops.ops_core.repositories.sqlalchemy import (
    SqlAlchemyOpsRepository,
)

from ..reporting import emit_json_report
from ..runtime import load_orchestration_runtime
from .service import ApprovalService

_DEFAULT_RESUME_TIMEOUT_SECONDS = 30.0
_DEFAULT_RESUME_POLL_INTERVAL_SECONDS = 0.5
_SCHEMA_NOT_READY_REASON = "Run input schema not found"

ResumeCallable = Callable[..., Any]
SleepCallable = Callable[[float], None]
ClockCallable = Callable[[], float]


class PrefectResumeReadinessTimeout(RuntimeError):
    """Raised when a newly suspended flow never becomes safely resumable."""


def _approval_payload(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "pipeline_run_id": record.pipeline_run_id,
        "node_id": record.node_id,
        "stage_id": record.stage_id,
        "policy": record.policy,
        "status": record.status,
        "requested_by": record.requested_by,
        "requested_at": record.requested_at.isoformat() if record.requested_at else None,
        "decided_by": record.decided_by,
        "decided_at": record.decided_at.isoformat() if record.decided_at else None,
        "reason": record.reason,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "details": dict(record.details or {}),
    }


def _is_transient_resume_rejection(exc: Exception) -> bool:
    """Return whether Prefect may still be publishing the paused input contract."""

    exception_type = type(exc)
    if (
        exception_type.__name__ == "NotPausedError"
        and exception_type.__module__.startswith("prefect")
    ):
        return True
    return isinstance(exc, RuntimeError) and _SCHEMA_NOT_READY_REASON in str(exc)


def resume_prefect_flow_run(
    flow_run_id: UUID | str,
    *,
    run_input: dict[str, Any],
    timeout_seconds: float = _DEFAULT_RESUME_TIMEOUT_SECONDS,
    poll_interval_seconds: float = _DEFAULT_RESUME_POLL_INTERVAL_SECONDS,
    resume_callable: ResumeCallable | None = None,
    sleep_callable: SleepCallable = time.sleep,
    clock_callable: ClockCallable = time.monotonic,
) -> dict[str, Any]:
    """Resume a protected flow with the input contract declared at suspension.

    The Ops database remains authoritative for the decision. Prefect RunInput is
    an acknowledgement that identifies the same approval and allows Prefect to
    load the suspended flow's declared input schema. A reviewer may decide just
    before the server observes PAUSED or just before the worker finishes saving
    that schema, so only those two exact readiness conditions are retried.
    """

    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must be greater than or equal to zero")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be greater than zero")
    if not isinstance(run_input, dict) or not run_input:
        raise ValueError("run_input must be a non-empty object")
    if resume_callable is None:
        from prefect.flow_runs import resume_flow_run

        resume_callable = resume_flow_run

    flow_uuid = UUID(str(flow_run_id))
    started = clock_callable()
    attempts = 0
    readiness_retries = 0

    while True:
        attempts += 1
        try:
            resume_callable(flow_uuid, run_input=run_input)
        except Exception as exc:
            if not _is_transient_resume_rejection(exc):
                raise
            elapsed = max(0.0, clock_callable() - started)
            if elapsed >= timeout_seconds:
                raise PrefectResumeReadinessTimeout(
                    "Prefect did not publish a resumable PAUSED state and RunInput "
                    f"schema within {timeout_seconds:g}s for flow run {flow_uuid}. "
                    "The approval decision remains authoritative in Ops DB; use the "
                    "approvals 'resume' command after the worker finishes suspension."
                ) from exc
            readiness_retries += 1
            remaining = timeout_seconds - elapsed
            sleep_callable(min(poll_interval_seconds, remaining))
            continue

        elapsed = max(0.0, clock_callable() - started)
        return {
            "flow_run_id": str(flow_uuid),
            "resumed": True,
            "attempt_count": attempts,
            "readiness_retries": readiness_retries,
            # Retain the old field for report consumers created by 0064f.
            "schema_wait_retries": readiness_retries,
            "elapsed_seconds": round(elapsed, 6),
        }


def _add_resume_timing_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--resume-timeout-seconds",
        type=float,
        default=_DEFAULT_RESUME_TIMEOUT_SECONDS,
    )
    command.add_argument(
        "--resume-poll-interval-seconds",
        type=float,
        default=_DEFAULT_RESUME_POLL_INTERVAL_SECONDS,
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="researchops-approvals")
    sub = result.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--status")
    listing.add_argument("--pipeline-run-id")
    listing.add_argument("--report-path")
    show = sub.add_parser("show")
    show.add_argument("--approval-id", required=True)
    show.add_argument("--report-path")
    for name in ("approve", "reject"):
        command = sub.add_parser(name)
        command.add_argument("--approval-id", required=True)
        command.add_argument("--actor", required=True)
        command.add_argument("--reason", required=True)
        command.add_argument("--resume-prefect", action="store_true")
        _add_resume_timing_arguments(command)
        command.add_argument("--report-path")
    resume = sub.add_parser("resume")
    resume.add_argument("--approval-id", required=True)
    _add_resume_timing_arguments(resume)
    resume.add_argument("--report-path")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    runtime = load_orchestration_runtime()
    with runtime.session_factory() as session:
        repository = SqlAlchemyOpsRepository(session)
        service = ApprovalService(repository)
        if args.command == "list":
            records = repository.list_approvals(
                status=args.status,
                pipeline_run_id=args.pipeline_run_id,
            )
            report = {
                "schema_version": "approval_list_v1",
                "count": len(records),
                "approvals": [_approval_payload(item) for item in records],
                "passed": True,
            }
        elif args.command == "show":
            record = repository.get_approval(args.approval_id)
            if record is None:
                raise SystemExit(f"Approval does not exist: {args.approval_id}")
            service.expire_if_needed(record, actor="approval-cli")
            report = {
                "schema_version": "approval_detail_v1",
                "approval": _approval_payload(record),
                "passed": True,
            }
        elif args.command == "resume":
            record = repository.get_approval(args.approval_id)
            if record is None:
                raise SystemExit(f"Approval does not exist: {args.approval_id}")
            service.expire_if_needed(record, actor="approval-cli")
            if record.status not in {"APPROVED", "REJECTED"}:
                raise SystemExit(
                    "Only an APPROVED or REJECTED decision can resume Prefect; "
                    f"observed {record.status}"
                )
            report = {
                "schema_version": "approval_resume_v1",
                "approval": _approval_payload(record),
                "passed": True,
            }
        else:
            decision = "APPROVED" if args.command == "approve" else "REJECTED"
            record = service.decide(
                args.approval_id,
                decision=decision,
                decided_by=args.actor,
                reason=args.reason,
            )
            report = {
                "schema_version": "approval_decision_v1",
                "approval": _approval_payload(record),
                "passed": True,
            }
        session.commit()

    should_resume = args.command == "resume" or getattr(
        args, "resume_prefect", False
    )
    if should_resume:
        approval = report["approval"]
        flow_run_id = approval["details"].get("prefect_flow_run_id")
        if not flow_run_id:
            raise SystemExit("Approval does not contain Prefect flow-run identity")
        run_input = {
            "approval_id": approval["id"],
            "acknowledgement": "decision-recorded",
        }
        try:
            resume_report = resume_prefect_flow_run(
                str(flow_run_id),
                run_input=run_input,
                timeout_seconds=args.resume_timeout_seconds,
                poll_interval_seconds=args.resume_poll_interval_seconds,
            )
        except Exception as exc:
            report["passed"] = False
            report["prefect_resume"] = {
                "flow_run_id": str(flow_run_id),
                "resumed": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            emit_json_report(report, report_path=args.report_path)
            raise
        report["prefect_resume"] = resume_report
        report["prefect_resumed"] = True
    emit_json_report(report, report_path=args.report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
