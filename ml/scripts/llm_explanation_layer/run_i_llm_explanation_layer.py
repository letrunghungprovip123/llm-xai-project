"""
Runner for Batch I - LLM Explanation Layer.

v0.1:
    Template-based explanation generator.

This runner:
- loads Batch H Explanation IR
- builds natural-language explanations using deterministic templates
- saves JSONL/CSV/report/manifest artifacts

It does NOT call any external LLM/API.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from ml.scripts.llm_explanation_layer.artifacts import (
    determine_batch_status,
    save_llm_explanation_artifacts,
)
from ml.scripts.llm_explanation_layer.config import (
    DEFAULT_RUN_MODE,
    GENERATOR_TYPE_TEMPLATE,
    SUPPORTED_RUN_MODES,
)
from ml.scripts.llm_explanation_layer.loaders import (
    load_llm_explanation_inputs,
)
from ml.scripts.llm_explanation_layer.template_generator import (
    build_template_explanations,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run Batch I - LLM Explanation Layer v0.1 template generator."
    )

    parser.add_argument(
        "--mode",
        default=DEFAULT_RUN_MODE,
        choices=SUPPORTED_RUN_MODES,
        help="Run mode: evaluation, inference, or auto.",
    )

    parser.add_argument(
        "--input-path",
        default=None,
        help=(
            "Optional path to Batch H explanation_ir.jsonl. "
            "If omitted, the default path for the selected mode is used."
        ),
    )

    parser.add_argument(
        "--generator",
        default=GENERATOR_TYPE_TEMPLATE,
        choices=[GENERATOR_TYPE_TEMPLATE],
        help="Generator type. v0.1 supports only 'template'.",
    )

    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Exit with code 1 if warnings are found.",
    )

    return parser.parse_args()


def main() -> int:
    """Main entrypoint."""
    args = parse_args()

    print("=" * 80)
    print("Batch I - LLM Explanation Layer")
    print("Stage: v0.1 template-based generator")
    print("External AI/API: disabled")
    print("=" * 80)

    print(f"Requested mode: {args.mode}")
    print(f"Generator: {args.generator}")

    if args.input_path:
        print(f"Input path: {args.input_path}")
    else:
        print("Input path: default by mode")

    try:
        inputs = load_llm_explanation_inputs(
            run_mode=args.mode,
            input_path=args.input_path,
        )
    except Exception as exc:
        print(f"[ERROR] Failed to load inputs: {exc}", file=sys.stderr)
        return 1

    print("-" * 80)
    print("Loaded IR inputs")
    print(f"Resolved mode: {inputs.run_mode}")
    print(f"Input path: {inputs.input_path}")
    print(f"IR record count: {len(inputs.ir_records)}")
    print(f"Has ground truth: {inputs.has_ground_truth}")
    print(f"Loader warnings: {len(inputs.warnings)}")
    print(f"Loader errors: {len(inputs.errors)}")

    if inputs.errors:
        print("[ERROR] Loader validation errors found:")
        for error in inputs.errors[:20]:
            print(f"  - {error}")
        return 1

    build_result = build_template_explanations(inputs.ir_records)

    print("-" * 80)
    print("Built template explanations")
    print(f"Explanation records: {len(build_result.explanation_records)}")
    print(f"Build warnings: {len(build_result.warnings)}")
    print(f"Build errors: {len(build_result.errors)}")

    artifact_paths = save_llm_explanation_artifacts(
        build_result=build_result,
        run_mode=inputs.run_mode,
        input_path=inputs.input_path,
        generator_type=args.generator,
    )

    status = determine_batch_status(build_result)

    print("-" * 80)
    print("Saved artifacts")
    for name, path in artifact_paths.items():
        print(f"{name}: {path}")

    print("-" * 80)
    print(f"Batch status: {status}")

    if build_result.warnings:
        print("\nWarnings preview:")
        for warning in build_result.warnings[:10]:
            print(f"  - {warning}")

    if build_result.errors:
        print("\nErrors preview:")
        for error in build_result.errors[:10]:
            print(f"  - {error}")

    if build_result.errors:
        return 1

    if args.fail_on_warnings and build_result.warnings:
        return 1

    print("=" * 80)
    print("Batch I template generation completed.")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())