from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy.orm import Session

from research.python.researchops.ops_core.db.engine import create_engine_from_settings
from research.python.researchops.ops_core.repositories.sqlalchemy import SqlAlchemyOpsRepository
from research.python.researchops.ops_core.settings import DatabaseSettings

from .contracts import GateEvaluationDraft
from .service import GateEvaluationService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="researchops-gates")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-contract")
    validate.add_argument("path")
    record = sub.add_parser("record")
    record.add_argument("path")
    record.add_argument("--actor", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--gate-id", required=True)
    inspect.add_argument("--scope-type", required=True)
    inspect.add_argument("--scope-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-contract":
        draft = GateEvaluationDraft.model_validate_json(Path(args.path).read_text())
        print(json.dumps(draft.model_dump(mode="json"), indent=2))
        return 0

    settings = DatabaseSettings.from_environment()
    assert settings is not None
    engine = create_engine_from_settings(settings)
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        if args.command == "record":
            draft = GateEvaluationDraft.model_validate_json(Path(args.path).read_text())
            result = GateEvaluationService(repo).record(draft, actor=args.actor)
            session.commit()
            print(json.dumps({
                "evaluation_id": result.evaluation.id,
                "gate_result_id": result.projection.id,
                "created": result.created,
            }, indent=2))
            return 0
        projection = repo.get_gate_result(args.gate_id, args.scope_type, args.scope_id)
        if projection is None:
            return 1
        print(json.dumps({
            "id": projection.id,
            "gate_id": projection.gate_id,
            "scope_type": projection.scope_type,
            "scope_id": projection.scope_id,
            "current_evaluation_id": projection.current_evaluation_id,
            "evaluation_outcome": projection.evaluation_outcome,
            "effective_status": projection.effective_status or projection.status,
        }, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
