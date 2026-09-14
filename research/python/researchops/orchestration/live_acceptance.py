from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any
from uuid import UUID

from research.python.researchops.ops_core.repositories.sqlalchemy import (
    SqlAlchemyOpsRepository,
)

from .reporting import emit_json_report
from .runtime import load_orchestration_runtime


def _state_name(flow_run: Any) -> str:
    return str(getattr(flow_run, "state_name", None) or "UNKNOWN").upper()


def run_deployment_command(
    *, name: str, parameters: dict[str, Any], timeout: int
) -> dict[str, Any]:
    from prefect.deployments import run_deployment

    flow_run = run_deployment(
        name=name,
        parameters=parameters,
        timeout=timeout,
        as_subflow=False,
    )
    return {
        "schema_version": "phase6_deployment_run_v1",
        "flow_run_id": str(flow_run.id),
        "state_name": _state_name(flow_run),
        "deployment_name": name,
        "passed": True,
    }


def wait_flow_run_command(*, flow_run_id: str, timeout: int) -> dict[str, Any]:
    from prefect.flow_runs import wait_for_flow_run

    flow_run = asyncio.run(
        wait_for_flow_run(
            UUID(flow_run_id), timeout=timeout, log_states=True
        )
    )
    return {
        "schema_version": "phase6_flow_run_wait_v1",
        "flow_run_id": str(flow_run.id),
        "state_name": _state_name(flow_run),
        "passed": True,
    }


def ops_summary(prefect_flow_run_id: str) -> dict[str, Any]:
    runtime = load_orchestration_runtime()
    with runtime.session_factory() as session:
        repository = SqlAlchemyOpsRepository(session)
        binding = repository.get_orchestration_binding_for_prefect(
            "prefect", prefect_flow_run_id, None
        )
        if binding is None:
            return {
                "schema_version": "phase6_ops_summary_v1",
                "passed": False,
                "error": "missing Prefect flow binding",
                "prefect_flow_run_id": prefect_flow_run_id,
            }
        pipeline = repository.get_pipeline_run(binding.pipeline_run_id)
        assert pipeline is not None
        stages = repository.list_stage_runs(pipeline.id)
        receipt = repository.get_pipeline_run_receipt(pipeline.id)
        approvals = repository.list_approvals(pipeline_run_id=pipeline.id)
        return {
            "schema_version": "phase6_ops_summary_v1",
            "passed": True,
            "prefect_flow_run_id": prefect_flow_run_id,
            "pipeline_run_id": pipeline.id,
            "flow_id": pipeline.flow_id,
            "pipeline_status": pipeline.status,
            "receipt_artifact_id": receipt.artifact_id if receipt else None,
            "stage_count": len(stages),
            "stage_attempts": [
                {
                    "stage_run_id": item.id,
                    "stage_id": item.stage_id,
                    "attempt": item.attempt,
                    "status": item.status,
                    "output_count": len(repository.stage_outputs(item.id)),
                }
                for item in stages
            ],
            "approvals": [
                {
                    "approval_id": item.id,
                    "status": item.status,
                    "policy": item.policy,
                    "node_id": item.node_id,
                    "stage_id": item.stage_id,
                }
                for item in approvals
            ],
        }


def latest_pending_approval(prefect_flow_run_id: str) -> dict[str, Any]:
    runtime = load_orchestration_runtime()
    with runtime.session_factory() as session:
        repository = SqlAlchemyOpsRepository(session)
        records = [
            item
            for item in repository.list_approvals(status="REQUESTED")
            if str((item.details or {}).get("prefect_flow_run_id"))
            == prefect_flow_run_id
        ]
        if not records:
            return {
                "schema_version": "phase6_pending_approval_v1",
                "passed": False,
                "prefect_flow_run_id": prefect_flow_run_id,
                "approval_id": None,
            }
        record = records[-1]
        return {
            "schema_version": "phase6_pending_approval_v1",
            "passed": True,
            "prefect_flow_run_id": prefect_flow_run_id,
            "approval_id": record.id,
            "pipeline_run_id": record.pipeline_run_id,
            "policy": record.policy,
            "status": record.status,
        }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="researchops-phase6-live")
    sub = result.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--deployment", required=True)
    run.add_argument("--parameters-json", default="{}")
    run.add_argument("--timeout", type=int, default=600)
    run.add_argument("--report-path")
    wait = sub.add_parser("wait")
    wait.add_argument("--flow-run-id", required=True)
    wait.add_argument("--timeout", type=int, default=600)
    wait.add_argument("--report-path")
    summary = sub.add_parser("ops-summary")
    summary.add_argument("--flow-run-id", required=True)
    summary.add_argument("--report-path")
    approval = sub.add_parser("pending-approval")
    approval.add_argument("--flow-run-id", required=True)
    approval.add_argument("--report-path")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "run":
        parameters = json.loads(args.parameters_json)
        if not isinstance(parameters, dict):
            raise SystemExit("--parameters-json must contain an object")
        report = run_deployment_command(
            name=args.deployment,
            parameters=parameters,
            timeout=args.timeout,
        )
    elif args.command == "wait":
        report = wait_flow_run_command(
            flow_run_id=args.flow_run_id, timeout=args.timeout
        )
    elif args.command == "ops-summary":
        report = ops_summary(args.flow_run_id)
    elif args.command == "pending-approval":
        report = latest_pending_approval(args.flow_run_id)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    emit_json_report(report, report_path=args.report_path)
    return 0 if report.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
