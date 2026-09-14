from __future__ import annotations

import argparse
from pathlib import Path

from .context import CommonXAIRunContext
from .evidence_stage import run_common_evidence
from .ir_stage import run_common_ir
from .xai_stage import run_common_xai

STAGE_ORDER = {"xai": 1, "ir": 2, "evidence": 3}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run dataset-neutral XAI → Explanation IR v3 → S0-S5 from a completed common-ML run."
    )
    parser.add_argument("--dataset-profile", type=Path, required=True)
    parser.add_argument("--canonical-bundle", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, default=None)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--source-run-id", required=True, help="Completed common-ML modeling run ID")
    parser.add_argument("--run-id", required=True, help="New isolated XAI/IR/evidence run ID")
    parser.add_argument("--start-at", choices=list(STAGE_ORDER), default="xai")
    parser.add_argument("--through", choices=list(STAGE_ORDER), default="evidence")
    parser.add_argument("--cases-per-group", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cases_per_group <= 0:
        raise ValueError("--cases-per-group must be positive")
    ctx = CommonXAIRunContext.load(
        dataset_profile_path=args.dataset_profile,
        canonical_bundle_path=args.canonical_bundle,
        experiment_id=args.experiment_id,
        source_run_id=args.source_run_id,
        run_id=args.run_id,
        artifact_root=args.artifact_root,
    )
    start = STAGE_ORDER[args.start_at]
    target = STAGE_ORDER[args.through]
    if start > target:
        raise ValueError("--start-at cannot be after --through")
    if start <= STAGE_ORDER["xai"] <= target:
        result = run_common_xai(ctx, cases_per_group=args.cases_per_group)
        print(
            "COMMON_XAI=PASS "
            f"cases={result.case_count} features={result.feature_count} "
            f"explainer={result.explainer_type} additivity_failed={result.failed_additivity_count}"
        )
    if start <= STAGE_ORDER["ir"] <= target:
        ir = run_common_ir(ctx)
        print(f"COMMON_IR_V3=PASS records={ir.record_count} warnings={ir.warning_count}")
    if start <= STAGE_ORDER["evidence"] <= target:
        evidence = run_common_evidence(ctx)
        print(
            "COMMON_EVIDENCE=PASS "
            f"cases={evidence.case_count} packages={evidence.package_count} quality={evidence.quality_status}"
        )
    print(f"COMMON_XAI_WORKSPACE={ctx.execution.workspace_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
