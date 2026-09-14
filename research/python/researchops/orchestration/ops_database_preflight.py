from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine, text

from research.python.researchops.ops_core.db.engine import create_engine_from_settings
from research.python.researchops.ops_core.settings import DatabaseSettings

from .reporting import emit_json_report


def check_ops_database(
    *,
    settings: DatabaseSettings | None = None,
    engine_factory: Callable[[DatabaseSettings], Engine] = create_engine_from_settings,
) -> dict[str, Any]:
    """Verify that the Prefect execution environment can reach the Ops database.

    The report never includes the database password. This check intentionally runs
    before the worker starts so a credential or network mismatch fails closed
    instead of producing accepted Prefect runs with no authoritative Ops binding.
    """

    resolved = settings or DatabaseSettings.from_environment()
    assert resolved is not None
    engine = engine_factory(resolved)
    try:
        with engine.connect() as connection:
            value = connection.execute(text("SELECT 1")).scalar_one()
        if value != 1:
            raise RuntimeError(f"Unexpected Ops database probe result: {value!r}")
        return {
            "schema_version": "prefect_ops_database_preflight_v1",
            "passed": True,
            "database_url": resolved.redacted_url,
            "probe": "SELECT 1",
        }
    finally:
        engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="researchops-prefect-ops-db-preflight")
    parser.add_argument("--report-path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = check_ops_database()
    except Exception as exc:
        settings = DatabaseSettings.from_environment(required=False)
        report = {
            "schema_version": "prefect_ops_database_preflight_v1",
            "passed": False,
            "database_url": settings.redacted_url if settings else None,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    emit_json_report(report, report_path=args.report_path)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
