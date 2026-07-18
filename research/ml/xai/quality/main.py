"""CLI mỏng cho XAI quality evaluation."""

from __future__ import annotations

import argparse
import traceback

from ..config import RUN_MODE_EVALUATION, SUPPORTED_RUN_MODES


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy quality pipeline và trả exit code."""

    parser = argparse.ArgumentParser(description="Chạy Batch G+ — XAI quality evaluation.")
    parser.add_argument("--mode", choices=SUPPORTED_RUN_MODES, default=RUN_MODE_EVALUATION)
    parser.add_argument("--skip-model-metrics", action="store_true")
    args = parser.parse_args(argv)

    from .pipeline import print_section, run_pipeline

    try:
        return run_pipeline(
            run_mode=args.mode,
            skip_model_metrics=args.skip_model_metrics,
        )
    except Exception as exc:
        print_section("Batch G+ failed")
        print("Error type:", type(exc).__name__)
        print("Error message:", exc)
        print("\nTraceback:")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
