"""Command-line interface for the Flow Catalog."""

from __future__ import annotations

import argparse
import json

from research.python.researchops.orchestration.reporting import emit_json_report

from .compiler import compile_payload, lock_matches, write_lock
from .graph import render_mermaid, render_text, topological_order
from .loader import load_flow_catalog
from .validator import validate_flow_catalog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="researchops-flow-catalog")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--report-path")
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("--check", action="store_true")
    compile_cmd.add_argument("--report-path")
    coverage = sub.add_parser("coverage")
    coverage.add_argument("--report-path")
    sub.add_parser("list")
    show = sub.add_parser("show")
    show.add_argument("flow_id")
    graph = sub.add_parser("graph")
    graph.add_argument("flow_id")
    graph.add_argument("--format", choices=("text", "mermaid"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    catalog = load_flow_catalog()
    if args.command == "validate":
        report = validate_flow_catalog(catalog)
        emit_json_report(report.to_dict(), report_path=args.report_path)
        return 0 if report.passed else 1
    if args.command == "coverage":
        report = validate_flow_catalog(catalog)
        payload = report.to_dict()
        payload["schema_version"] = "flow_catalog_coverage_v1"
        emit_json_report(payload, report_path=args.report_path)
        return 0 if report.passed and not report.missing_stage_ids else 1
    if args.command == "compile":
        if args.check:
            passed = lock_matches()
            payload = {
                "schema_version": "flow_catalog_lock_check_v1",
                "passed": passed,
                "message": (
                    "Flow Catalog lock is current."
                    if passed
                    else "Flow Catalog lock is missing or stale."
                ),
            }
            emit_json_report(payload, report_path=args.report_path)
            return 0 if passed else 1
        target = write_lock()
        payload = compile_payload()
        payload["written_to"] = str(target)
        emit_json_report(payload, report_path=args.report_path)
        return 0
    if args.command == "list":
        for flow in sorted(catalog.flows, key=lambda item: item.id):
            print(
                f"{flow.id:38} {flow.status:8} {flow.work_queue:13} "
                f"{flow.terminal_gate}"
            )
        return 0
    flow = catalog.by_id().get(args.flow_id)
    if flow is None:
        raise SystemExit(f"Unknown flow: {args.flow_id}")
    if args.command == "show":
        payload = flow.model_dump(mode="json", exclude_none=True)
        payload["topological_order"] = (
            topological_order(flow) if flow.status != "PLANNED" else []
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.command == "graph":
        if flow.status == "PLANNED":
            raise SystemExit(f"Flow {flow.id} is PLANNED and has no executable DAG")
        print(render_mermaid(flow) if args.format == "mermaid" else render_text(flow))
        return 0
    raise AssertionError(args.command)
