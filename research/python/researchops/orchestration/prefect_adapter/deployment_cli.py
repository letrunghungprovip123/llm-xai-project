from __future__ import annotations

import argparse

from ..reporting import emit_json_report
from .deployments import (
    bootstrap_deployments,
    deployment_lock_matches,
    load_deployment_catalog,
    validate_deployment_catalog,
    validate_deployment_imports,
    write_deployment_lock,
    write_prefect_yaml,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="researchops-prefect-deployments")
    sub = result.add_subparsers(dest="command", required=True)
    for name in ("validate", "compile", "import-check", "bootstrap"):
        command = sub.add_parser(name)
        command.add_argument("--report-path")
    sub.add_parser("compile-check").add_argument("--report-path")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "validate":
        report = validate_deployment_catalog()
    elif args.command == "compile":
        yaml_path = write_prefect_yaml()
        lock_path = write_deployment_lock()
        report = {
            "schema_version": "prefect_deployments_compile_v1",
            "passed": True,
            "prefect_yaml": str(yaml_path),
            "lock_path": str(lock_path),
            "deployment_count": len(load_deployment_catalog().deployments),
        }
    elif args.command == "compile-check":
        report = {
            "schema_version": "prefect_deployments_lock_check_v1",
            "passed": deployment_lock_matches(),
        }
    elif args.command == "import-check":
        report = validate_deployment_imports()
    elif args.command == "bootstrap":
        validation = validate_deployment_catalog()
        if not validation["passed"]:
            emit_json_report(validation, report_path=args.report_path)
            return 1
        import_validation = validate_deployment_imports()
        if not import_validation["passed"]:
            report = {
                "schema_version": "prefect_deployments_bootstrap_v1",
                "passed": False,
                "deployment_count": validation["deployment_count"],
                "import_validation": import_validation,
                "errors": import_validation["errors"],
            }
            emit_json_report(report, report_path=args.report_path)
            return 1
        print("PREFECT_DEPLOYMENT_IMPORT_PREFLIGHT=PASS")
        bootstrap_deployments(validate_imports=False)
        report = {
            "schema_version": "prefect_deployments_bootstrap_v1",
            "passed": True,
            "deployment_count": validation["deployment_count"],
            "import_validation": import_validation,
            "idempotent": True,
        }
    else:  # pragma: no cover
        raise AssertionError(args.command)
    emit_json_report(report, report_path=args.report_path)
    return 0 if report.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
