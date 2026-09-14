"""CLI for validating, compiling and inspecting the Stage Registry."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from research.python.researchops.contracts.io import project_root

from .command_renderer import resolve_command
from .compiler import compile_payload, lock_matches, write_lock
from .graph import dependency_map, mermaid_graph, topological_order
from .loader import load_stage_registry
from .validator import dispatcher_stage_names, validate_stage_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m research.python.researchops.stage_registry"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--json", action="store_true", dest="as_json")

    compile_command = commands.add_parser("compile")
    compile_command.add_argument("--check", action="store_true")

    list_command = commands.add_parser("list")
    list_command.add_argument("--status", choices=["ACTIVE", "OPTIONAL", "LEGACY"])

    show = commands.add_parser("show")
    show.add_argument("stage_id")

    graph = commands.add_parser("graph")
    graph.add_argument("--format", choices=["mermaid", "json"], default="mermaid")

    commands.add_parser("coverage")

    verify = commands.add_parser("verify-command")
    verify.add_argument("stage_id")
    verify.add_argument("--strict-executable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = project_root()

    if args.command == "validate":
        report = validate_stage_registry(root)
        if args.as_json:
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(
                f"Stages: {report.stage_count} "
                f"(active={report.active_count}, optional={report.optional_count}, "
                f"legacy={report.legacy_count})"
            )
            print(f"Dispatcher coverage target: {report.dispatcher_stage_count}")
            if report.passed:
                print("Result: STAGE_REGISTRY_VALID")
            else:
                print("Result: STAGE_REGISTRY_INVALID")
                for issue in report.issues:
                    prefix = f"{issue.stage_id}: " if issue.stage_id else ""
                    print(f"- [{issue.code}] {prefix}{issue.message}")
        return 0 if report.passed else 1

    if args.command == "compile":
        if args.check:
            matches = lock_matches(root)
            print("Stage Registry lock is current." if matches else "Stage Registry lock drift detected.")
            return 0 if matches else 1
        path = write_lock(root)
        payload = compile_payload(root)
        print(f"Wrote: {path.relative_to(root)}")
        print(f"Registry SHA-256: {payload['registry_sha256']}")
        return 0

    registry = load_stage_registry(root=root)
    by_id = registry.by_id()

    if args.command == "list":
        for stage in sorted(registry.stages, key=lambda item: item.id):
            if args.status and stage.status != args.status:
                continue
            print(f"{stage.id:<38} {stage.status:<8} {stage.verification.success_gate}")
        return 0

    if args.command == "show":
        stage = by_id.get(args.stage_id)
        if stage is None:
            print(f"Unknown stage: {args.stage_id}")
            return 2
        print(json.dumps(stage.model_dump(mode="json", exclude_none=True), indent=2))
        return 0

    if args.command == "graph":
        if args.format == "mermaid":
            print(mermaid_graph(registry), end="")
        else:
            dependencies = {
                key: sorted(value) for key, value in dependency_map(registry).items()
            }
            print(json.dumps(dependencies, indent=2, sort_keys=True))
        return 0

    if args.command == "coverage":
        dispatcher = dispatcher_stage_names(root)
        declared = {
            stage.legacy_dispatcher_stage
            for stage in registry.stages
            if stage.legacy_dispatcher_stage is not None
        }
        print(f"Registry stages: {len(registry.stages)}")
        print(f"TypeScript dispatcher stages: {len(dispatcher)}")
        print(f"Covered dispatcher stages: {len(dispatcher & declared)}")
        print(f"Missing: {sorted(dispatcher - declared)}")
        print(f"Unknown: {sorted(declared - dispatcher)}")
        print(f"Topological stages: {len(topological_order(registry))}")
        return 0 if dispatcher == declared else 1

    if args.command == "verify-command":
        stage = by_id.get(args.stage_id)
        if stage is None:
            print(f"Unknown stage: {args.stage_id}")
            return 2
        resolution = resolve_command(stage, root)
        print(" ".join(resolution.rendered))
        for detail in resolution.details:
            print(f"- {detail}")
        if not resolution.structurally_valid:
            return 1
        if args.strict_executable and not resolution.executable_available:
            return 1
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")
