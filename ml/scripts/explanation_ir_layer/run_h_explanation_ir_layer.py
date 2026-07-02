"""
Runner for Batch H - Concept-aware Explanation IR Layer.

This runner converts Batch G structured XAI evidence into Explanation IR.

Main input:
    data/reports/xai/xai_local_evidence.jsonl

Main output:
    data/reports/explanation_ir/<mode>/explanation_ir.jsonl

Other outputs:
    data/reports/explanation_ir/<mode>/explanation_ir_summary.csv
    data/reports/explanation_ir/<mode>/explanation_ir_quality_report.json
    data/manifests/explanation_ir_manifest_<mode>.json

Important:
- This runner does NOT read raw Home Credit data.
- This runner does NOT load the ML model.
- This runner does NOT compute SHAP again.
- This runner does NOT call an LLM.
- This runner does NOT generate final user-facing explanation text.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from ml.scripts.explanation_ir_layer.config import (
    BATCH_NAME,
    BATCH_SHORT_NAME,
    DEFAULT_RUN_MODE,
    RUN_MODE_AUTO,
    RUN_MODE_EVALUATION,
    RUN_MODE_INFERENCE,
    SUPPORTED_RUN_MODES,
    get_config_summary,
)
from ml.scripts.explanation_ir_layer.loaders import (
    load_xai_evidence_inputs,
    summarize_loaded_inputs,
)
from ml.scripts.explanation_ir_layer.ir_builder import (
    build_explanation_ir_records,
)
from ml.scripts.explanation_ir_layer.artifacts import (
    save_explanation_ir_artifacts,
)


# =============================================================================
# CLI
# =============================================================================

def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Batch H - Convert structured XAI evidence into concept-aware "
            "Explanation IR."
        )
    )

    parser.add_argument(
        "--mode",
        type=str,
        default=DEFAULT_RUN_MODE,
        choices=SUPPORTED_RUN_MODES,
        help=(
            "Run mode. "
            "'evaluation' uses labeled test-set evidence. "
            "'inference' uses unlabeled inference evidence. "
            "'auto' detects mode from evidence records. "
            f"Default: {DEFAULT_RUN_MODE}"
        ),
    )

    parser.add_argument(
        "--input-path",
        type=str,
        default=None,
        help=(
            "Optional override path to xai_local_evidence.jsonl. "
            "Useful while Batch G still writes to a shared default path."
        ),
    )

    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print config summary before running.",
    )

    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help=(
            "Exit with non-zero status if the batch finishes with warnings. "
            "Useful for stricter CI checks."
        ),
    )

    return parser.parse_args()


# =============================================================================
# Pretty printing
# =============================================================================

def print_section(title: str) -> None:
    """
    Print a section header.
    """
    print()
    print("=" * 88)
    print(title)
    print("=" * 88)


def print_kv(key: str, value: object) -> None:
    """
    Print a key-value line.
    """
    print(f"{key}: {value}")


def print_json(data: dict) -> None:
    """
    Pretty-print JSON dictionary.
    """
    print(json.dumps(data, indent=2, ensure_ascii=False))


# =============================================================================
# Runner
# =============================================================================

def run_batch_h(
    run_mode: str = DEFAULT_RUN_MODE,
    input_path: Optional[str | Path] = None,
    print_config: bool = False,
    fail_on_warnings: bool = False,
) -> int:
    """
    Run Batch H end-to-end.

    Returns:
        process exit code
    """
    print_section(f"{BATCH_NAME} ({BATCH_SHORT_NAME})")

    print_kv("Requested run mode", run_mode)
    print_kv("Input path override", input_path if input_path else "None")

    if print_config:
        print_section("Config Summary")
        print_json(get_config_summary(run_mode=run_mode, input_path=input_path))

    # -------------------------------------------------------------------------
    # Step 1 - Load XAI evidence records
    # -------------------------------------------------------------------------
    print_section("Step 1 - Load XAI evidence records")

    try:
        inputs = load_xai_evidence_inputs(
            run_mode=run_mode,
            input_path=input_path,
        )
    except Exception as exc:
        print("[FAILED] Could not load XAI evidence inputs.")
        print(f"Error: {exc}")
        return 1

    loaded_summary = summarize_loaded_inputs(inputs)

    print_kv("Resolved run mode", inputs.run_mode)
    print_kv("Has ground truth", inputs.has_ground_truth)
    print_kv("Input path", inputs.input_path)
    print_kv("Evidence record count", inputs.record_count)
    print_kv("Loader warning count", len(inputs.warnings))

    if inputs.warnings:
        print()
        print("Loader warnings:")
        for warning in inputs.warnings[:20]:
            print(f"  - {warning}")

        if len(inputs.warnings) > 20:
            print(f"  ... {len(inputs.warnings) - 20} more warnings")

    # -------------------------------------------------------------------------
    # Step 2 - Build Explanation IR records
    # -------------------------------------------------------------------------
    print_section("Step 2 - Build Explanation IR records")

    try:
        build_result = build_explanation_ir_records(
            evidence_records=inputs.evidence_records,
            run_mode=inputs.run_mode,
            has_ground_truth=inputs.has_ground_truth,
            source_file=inputs.input_path,
        )
    except Exception as exc:
        print("[FAILED] Could not build Explanation IR records.")
        print(f"Error: {exc}")
        return 1

    print_kv("IR record count", len(build_result.ir_records))
    print_kv("IR dict count", len(build_result.ir_record_dicts))
    print_kv("Summary row count", len(build_result.summary_df))
    print_kv("Builder warning count", len(build_result.warnings))
    print_kv("Builder error count", len(build_result.errors))

    if build_result.warnings:
        print()
        print("Builder warnings:")
        for warning in build_result.warnings[:20]:
            print(f"  - {warning}")

        if len(build_result.warnings) > 20:
            print(f"  ... {len(build_result.warnings) - 20} more warnings")

    if build_result.errors:
        print()
        print("Builder errors:")
        for error in build_result.errors[:20]:
            print(f"  - {error}")

        if len(build_result.errors) > 20:
            print(f"  ... {len(build_result.errors) - 20} more errors")

    if len(build_result.ir_records) == 0:
        print("[FAILED] No Explanation IR records were produced.")
        return 1

    # -------------------------------------------------------------------------
    # Step 3 - Save artifacts
    # -------------------------------------------------------------------------
    print_section("Step 3 - Save Explanation IR artifacts")

    try:
        save_result = save_explanation_ir_artifacts(
            build_result=build_result,
            run_mode=inputs.run_mode,
            has_ground_truth=inputs.has_ground_truth,
            input_path=inputs.input_path,
        )
    except Exception as exc:
        print("[FAILED] Could not save Explanation IR artifacts.")
        print(f"Error: {exc}")
        return 1

    print_kv("Final status", save_result.status)
    print_kv("Run mode", save_result.run_mode)
    print_kv("Save warning count", len(save_result.warnings))
    print_kv("Save error count", len(save_result.errors))

    print()
    print("Output paths:")
    print_kv("explanation_ir_jsonl", save_result.artifact_paths.explanation_ir_jsonl)
    print_kv("summary_csv", save_result.artifact_paths.explanation_ir_summary_csv)
    print_kv(
        "quality_report",
        save_result.artifact_paths.explanation_ir_quality_report_json,
    )
    print_kv("manifest", save_result.artifact_paths.explanation_ir_manifest_json)

    print()
    print("Output path status:")
    for key, value in save_result.output_path_status.items():
        print(f"  {key}: {value}")

    # -------------------------------------------------------------------------
    # Step 4 - Final quality summary
    # -------------------------------------------------------------------------
    print_section("Step 4 - Final quality summary")

    quality_report = save_result.quality_report

    print_kv("Status", quality_report.get("status"))
    print_kv("Run mode", quality_report.get("run_mode"))
    print_kv("Has ground truth", quality_report.get("has_ground_truth"))

    record_counts = quality_report.get("record_counts", {})
    claim_counts = quality_report.get("claim_counts", {})
    factor_counts = quality_report.get("factor_counts", {})
    quality_checks = quality_report.get("quality_checks", {})

    print()
    print("Record counts:")
    for key, value in record_counts.items():
        print(f"  {key}: {value}")

    print()
    print("Claim counts:")
    for key, value in claim_counts.items():
        print(f"  {key}: {value}")

    print()
    print("Factor counts:")
    for key, value in factor_counts.items():
        print(f"  {key}: {value}")

    print()
    print("Quality checks:")
    for key, value in quality_checks.items():
        print(f"  {key}: {value}")

    # -------------------------------------------------------------------------
    # Exit code
    # -------------------------------------------------------------------------
    if save_result.status == "FAILED":
        print()
        print("[FAILED] Batch H finished with FAILED status.")
        return 1

    if fail_on_warnings and save_result.status == "PASSED_WITH_WARNINGS":
        print()
        print("[FAILED] Batch H finished with warnings and --fail-on-warnings is set.")
        return 1

    print()
    print("[DONE] Batch H completed.")
    return 0


def main() -> None:
    """
    Main CLI entrypoint.
    """
    args = parse_args()

    exit_code = run_batch_h(
        run_mode=args.mode,
        input_path=args.input_path,
        print_config=args.print_config,
        fail_on_warnings=args.fail_on_warnings,
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()