"""CLI mỏng cho Explanation IR v2."""

from __future__ import annotations

import argparse

from .config import DEFAULT_RUN_MODE, SUPPORTED_RUN_MODES


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy IR builder và trả exit code."""

    parser = argparse.ArgumentParser(description="Xây quality-aware Explanation IR v2.")
    parser.add_argument("--mode", default=DEFAULT_RUN_MODE, choices=SUPPORTED_RUN_MODES)
    parser.add_argument("--input-path", default=None)
    parser.add_argument("--xai-quality-summary-path", default=None)
    parser.add_argument("--xai-concept-aggregation-path", default=None)
    parser.add_argument("--xai-quality-manifest-path", default=None)
    parser.add_argument("--print-config", action="store_true")
    parser.add_argument("--fail-on-warnings", action="store_true")
    args = parser.parse_args(argv)

    from .pipeline import run_batch_h

    return run_batch_h(
        run_mode=args.mode,
        input_path=args.input_path,
        xai_quality_summary_path=args.xai_quality_summary_path,
        xai_concept_aggregation_path=args.xai_concept_aggregation_path,
        xai_quality_manifest_path=args.xai_quality_manifest_path,
        print_config=args.print_config,
        fail_on_warnings=args.fail_on_warnings,
    )


if __name__ == "__main__":
    raise SystemExit(main())
