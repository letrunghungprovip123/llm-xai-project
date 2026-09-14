from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .bootstrap import bootstrap_prefect_runtime
from .contracts import (
    load_prefect_runtime_contract,
    validate_prefect_runtime_contract,
)
from .execution.validation import validate_execution_contracts
from .gateway import RealPrefectGateway
from .reporting import emit_json_report
from .settings import PrefectSettings, write_local_environment


def _report_path(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--report-path")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="researchops-orchestration")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-runtime")
    _report_path(validate)
    init = sub.add_parser("init-local-env")
    init.add_argument("--output", default=".env.researchops-prefect.local")
    init.add_argument("--force", action="store_true")
    check = sub.add_parser("check-config")
    _report_path(check)
    health = sub.add_parser("health")
    _report_path(health)
    bootstrap = sub.add_parser("bootstrap-runtime")
    _report_path(bootstrap)
    inspect = sub.add_parser("inspect-runtime")
    _report_path(inspect)
    execution = sub.add_parser("validate-execution-contracts")
    _report_path(execution)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report_path = getattr(args, "report_path", None)
    if args.command == "validate-runtime":
        emit_json_report(
            validate_prefect_runtime_contract(),
            report_path=report_path,
        )
        return 0
    if args.command == "validate-execution-contracts":
        report = validate_execution_contracts()
        emit_json_report(report, report_path=report_path)
        return 0 if report["passed"] else 1
    if args.command == "init-local-env":
        target = write_local_environment(Path(args.output), overwrite=args.force)
        emit_json_report(
            {"created": str(target), "mode": oct(target.stat().st_mode & 0o777)}
        )
        return 0

    settings = PrefectSettings.from_environment()
    if args.command == "check-config":
        emit_json_report(settings.redacted_dict(), report_path=report_path)
        return 0

    contract = load_prefect_runtime_contract()
    gateway = RealPrefectGateway()
    if args.command in {"health", "inspect-runtime"}:
        snapshot = asyncio.run(gateway.inspect(contract))
        emit_json_report(snapshot.to_dict(), report_path=report_path)
        return 0 if snapshot.passed else 1
    if args.command == "bootstrap-runtime":
        snapshot = asyncio.run(bootstrap_prefect_runtime(gateway, contract))
        payload = snapshot.to_dict()
        payload["schema_version"] = "prefect_runtime_bootstrap_v1"
        payload["idempotent"] = True
        emit_json_report(payload, report_path=report_path)
        return 0
    raise AssertionError(args.command)
