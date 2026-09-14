from __future__ import annotations

import argparse
from pathlib import Path

from .context import CommonMLRunContext
from .modeling import run_common_modeling
from .preprocessing import run_common_preprocessing
from .split import run_common_split


STAGE_ORDER = {"split": 1, "preprocessing": 2, "modeling": 3}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run dataset-neutral common ML stages without touching legacy Home Credit outputs."
    )
    parser.add_argument("--dataset-profile", type=Path, required=True)
    parser.add_argument("--canonical-bundle", type=Path, required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-root", type=Path, default=None)
    parser.add_argument(
        "--through",
        choices=list(STAGE_ORDER),
        default="modeling",
        help="Run from split through the selected common ML stage.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ctx = CommonMLRunContext.load(
        dataset_profile_path=args.dataset_profile,
        canonical_bundle_path=args.canonical_bundle,
        experiment_id=args.experiment_id,
        run_id=args.run_id,
        artifact_root=args.artifact_root,
    )
    split_result = run_common_split(ctx)
    print(
        "COMMON_ML_SPLIT=PASS "
        f"train={split_result.train_rows} valid={split_result.valid_rows} test={split_result.test_rows} "
        f"features={split_result.model_feature_count}"
    )
    if STAGE_ORDER[args.through] >= STAGE_ORDER["preprocessing"]:
        prep_result = run_common_preprocessing(ctx)
        print(
            "COMMON_ML_PREPROCESSING=PASS "
            f"tree_features={prep_result.tree_feature_count} "
            f"linear_features={prep_result.linear_feature_count}"
        )
    if STAGE_ORDER[args.through] >= STAGE_ORDER["modeling"]:
        model_result = run_common_modeling(ctx)
        print(
            "COMMON_ML_MODELING=PASS "
            f"best_model={model_result.best_model_name} "
            f"branch={model_result.best_model_branch}"
        )
    print(f"COMMON_ML_WORKSPACE={ctx.execution.workspace_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
