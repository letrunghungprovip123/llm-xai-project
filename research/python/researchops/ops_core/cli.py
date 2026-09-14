from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config

from .db.alembic_config import set_explicit_database_url
from .settings import DatabaseSettings


def _config() -> Config:
    root = Path(__file__).resolve().parents[4]
    config = Config(str(root / "alembic.ini"))
    settings = DatabaseSettings.from_environment()
    assert settings is not None
    set_explicit_database_url(config, settings.url)
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ResearchOps operational database")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-config")
    sub.add_parser("upgrade")
    downgrade = sub.add_parser("downgrade")
    downgrade.add_argument("revision", default="-1", nargs="?")
    sub.add_parser("current")
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--mode", choices=["report-only", "repair-safe"], default="report-only")
    reconcile.add_argument("--artifact-profile", default="development-filesystem")
    reconcile.add_argument("--actor", default="cli-reconciler")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "reconcile":
        import json
        from research.python.researchops.artifacts.profiles import load_store
        from .db.engine import create_engine_from_settings, create_session_factory
        from .repositories.sqlalchemy import SqlAlchemyOpsRepository
        from .services.reconciliation import ReconciliationService
        settings = DatabaseSettings.from_environment()
        assert settings is not None
        engine = create_engine_from_settings(settings)
        factory = create_session_factory(engine)
        with factory.begin() as session:
            service = ReconciliationService(SqlAlchemyOpsRepository(session), load_store(args.artifact_profile))
            report = service.inspect() if args.mode == "report-only" else service.repair_safe(actor=args.actor)
            print(json.dumps(report.__dict__, indent=2))
            return 0 if report.passed else 2
    if args.command == "check-config":
        settings = DatabaseSettings.from_environment()
        assert settings is not None
        print(settings.redacted_url)
        return 0
    config = _config()
    if args.command == "upgrade":
        command.upgrade(config, "head")
    elif args.command == "downgrade":
        command.downgrade(config, args.revision)
    elif args.command == "current":
        command.current(config, verbose=True)
    return 0
