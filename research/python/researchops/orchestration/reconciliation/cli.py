from __future__ import annotations

import argparse
import re

from ..reporting import emit_json_report
from ..runtime import load_orchestration_runtime
from .gateway import LivePrefectSnapshotGateway
from .service import ReconciliationService


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _acceptance_session(value: str) -> str:
    if re.fullmatch(r"[a-z0-9-]+", value) is None:
        raise argparse.ArgumentTypeError("must match ^[a-z0-9-]+$")
    return value


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="researchops-prefect-reconcile")
    result.add_argument(
        "--mode", choices=("report-only", "repair-safe"), default="report-only"
    )
    result.add_argument("--report-path")
    result.add_argument(
        "--acceptance-session",
        type=_acceptance_session,
        help=(
            "Reconcile only Prefect and Ops records belonging to one Phase 6 "
            "acceptance session. Historical runs remain visible to global audits "
            "but cannot fail the current-session acceptance gate."
        ),
    )
    result.add_argument(
        "--limit",
        type=_positive_int,
        default=1000,
        help=(
            "Maximum total flow runs and task runs to reconcile. "
            "The Prefect API is read in pages of at most 200 records."
        ),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = ReconciliationService(
        load_orchestration_runtime(),
        LivePrefectSnapshotGateway(limit=args.limit),
        acceptance_session=args.acceptance_session,
    ).run(args.mode)
    emit_json_report(report.model_dump(mode="json"), report_path=args.report_path)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
