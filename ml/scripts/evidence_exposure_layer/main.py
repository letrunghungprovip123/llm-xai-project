import argparse
import sys
from pathlib import Path

from config import DEFAULT_RUN_MODE, INPUT_IR_PATH, OUTPUT_DIR, MANIFEST_DIR
from loaders import load_ir_records
from package_builder import build_all_packages_for_ir
from artifacts import write_all_artifacts


# Lấy path mặc định theo run mode nhưng vẫn giữ command cũ cho evaluation.
def resolve_paths(args):
    run_mode = args.run_mode

    if args.input:
        input_path = Path(args.input)
    elif run_mode == DEFAULT_RUN_MODE:
        input_path = INPUT_IR_PATH
    else:
        input_path = Path(
            f"data/reports/explanation_ir_v2/{run_mode}/explanation_ir_v2.jsonl"
        )

    if args.output_dir:
        output_dir = Path(args.output_dir)
    elif run_mode == DEFAULT_RUN_MODE:
        output_dir = OUTPUT_DIR
    else:
        output_dir = Path(f"data/reports/evidence_exposure/{run_mode}")

    manifest_dir = Path(args.manifest_dir) if args.manifest_dir else MANIFEST_DIR

    return input_path, output_dir, manifest_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-mode",
        choices=("development", "evaluation"),
        default=DEFAULT_RUN_MODE,
    )
    parser.add_argument("--input", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--manifest-dir", default=str(MANIFEST_DIR))
    parser.add_argument(
        "--disallow-overlap-with",
        default=None,
        help="Optional IR JSONL path that must not share source IDs with this run.",
    )
    args = parser.parse_args()

    input_path, output_dir, manifest_dir = resolve_paths(args)
    ir_records = load_ir_records(input_path)

    if args.disallow_overlap_with:
        reference_records = load_ir_records(args.disallow_overlap_with)
        current_ids = {
            item.get("ir_id") or item.get("source_ir_id")
            for item in ir_records
        }
        reference_ids = {
            item.get("ir_id") or item.get("source_ir_id")
            for item in reference_records
        }
        current_ids.discard(None)
        reference_ids.discard(None)
        overlap = current_ids.intersection(reference_ids)

        if overlap:
            examples = sorted(str(x) for x in overlap)[:10]
            raise ValueError(
                f"Development/evaluation overlap found: {len(overlap)} IDs. "
                f"Examples: {examples}"
            )

    packages = []
    for ir in ir_records:
        ir["run_mode"] = args.run_mode
        packages.extend(build_all_packages_for_ir(ir))

    quality_report = write_all_artifacts(
        packages=packages,
        ir_records=ir_records,
        output_dir=output_dir,
        manifest_dir=manifest_dir,
        input_path=input_path,
        run_mode=args.run_mode,
    )

    print(f"Batch I0 status: {quality_report.get('status')}")
    print(f"Run mode: {args.run_mode}")
    print(f"Input IR records: {quality_report.get('input_ir_record_count')}")
    print(f"Output packages: {quality_report.get('output_package_count')}")
    print(f"Prompt leakage findings: {quality_report.get('prompt_leakage_finding_count')}")
    print(f"S1-S2 feature mismatches: {quality_report.get('s1_s2_feature_order_mismatch_count')}")
    print(f"S4-S5 evidence mismatches: {quality_report.get('s4_s5_evidence_mismatch_count')}")

    if quality_report.get("status") == "FAILED":
        sys.exit(1)


if __name__ == "__main__":
    main()
