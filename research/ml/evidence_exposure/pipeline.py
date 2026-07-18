"""Orchestration evidence exposure S0–S5, không chứa CLI parsing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_all_artifacts
from .config import DEFAULT_RUN_MODE, INPUT_IR_PATH, MANIFEST_DIR, OUTPUT_DIR
from .loaders import load_ir_records
from .package_builder import build_all_packages_for_ir


def resolve_paths(
    run_mode: str,
    input_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    manifest_dir: str | Path | None = None,
) -> tuple[Path, Path, Path]:
    """Giữ nguyên default path theo run mode của command lịch sử."""

    if input_path is not None:
        resolved_input = Path(input_path)
    elif run_mode == DEFAULT_RUN_MODE:
        resolved_input = INPUT_IR_PATH
    else:
        resolved_input = Path(
            f"data/reports/explanation_ir_v2/{run_mode}/explanation_ir_v2.jsonl"
        )

    if output_dir is not None:
        resolved_output = Path(output_dir)
    elif run_mode == DEFAULT_RUN_MODE:
        resolved_output = OUTPUT_DIR
    else:
        resolved_output = Path(f"data/reports/evidence_exposure/{run_mode}")

    resolved_manifest = Path(manifest_dir) if manifest_dir is not None else MANIFEST_DIR
    return resolved_input, resolved_output, resolved_manifest


def source_ids(records: list[dict[str, Any]]) -> set[Any]:
    """Lấy source IR IDs để kiểm tra development/evaluation overlap."""

    values = {
        record.get("ir_id") or record.get("source_ir_id")
        for record in records
    }
    values.discard(None)
    return values


def ensure_disjoint_source_ids(
    current_records: list[dict[str, Any]],
    reference_records: list[dict[str, Any]],
) -> None:
    """Fail-fast khi hai cohort chia sẻ source IR ID."""

    overlap = source_ids(current_records).intersection(source_ids(reference_records))
    if overlap:
        examples = sorted(str(value) for value in overlap)[:10]
        raise ValueError(
            f"Development/evaluation overlap found: {len(overlap)} IDs. "
            f"Examples: {examples}"
        )


def build_evidence_packages(
    ir_records: list[dict[str, Any]],
    run_mode: str,
) -> list[dict[str, Any]]:
    """Xây đúng sáu package S0–S5 cho từng IR record, giữ nguyên record order."""

    packages: list[dict[str, Any]] = []
    for ir_record in ir_records:
        ir_record["run_mode"] = run_mode
        packages.extend(build_all_packages_for_ir(ir_record))
    return packages


def run_evidence_exposure(
    run_mode: str = DEFAULT_RUN_MODE,
    input_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    manifest_dir: str | Path | None = None,
    disallow_overlap_with: str | Path | None = None,
) -> dict[str, Any]:
    """Load IR, kiểm tra cohort, build packages rồi ghi artifacts."""

    resolved_input, resolved_output, resolved_manifest = resolve_paths(
        run_mode=run_mode,
        input_path=input_path,
        output_dir=output_dir,
        manifest_dir=manifest_dir,
    )
    ir_records = load_ir_records(resolved_input)

    if disallow_overlap_with is not None:
        reference_records = load_ir_records(disallow_overlap_with)
        ensure_disjoint_source_ids(ir_records, reference_records)

    packages = build_evidence_packages(ir_records, run_mode)
    quality_report = write_all_artifacts(
        packages=packages,
        ir_records=ir_records,
        output_dir=resolved_output,
        manifest_dir=resolved_manifest,
        input_path=resolved_input,
        run_mode=run_mode,
    )
    print_quality_summary(quality_report, run_mode)
    return quality_report


def print_quality_summary(quality_report: dict[str, Any], run_mode: str) -> None:
    """In đúng các quality counters lịch sử của Batch I0."""

    print(f"Batch I0 status: {quality_report.get('status')}")
    print(f"Run mode: {run_mode}")
    print(f"Input IR records: {quality_report.get('input_ir_record_count')}")
    print(f"Output packages: {quality_report.get('output_package_count')}")
    print(f"Prompt leakage findings: {quality_report.get('prompt_leakage_finding_count')}")
    print(f"S1-S2 feature mismatches: {quality_report.get('s1_s2_feature_order_mismatch_count')}")
    print(f"S4-S5 evidence mismatches: {quality_report.get('s4_s5_evidence_mismatch_count')}")
