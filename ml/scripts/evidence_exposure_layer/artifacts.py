import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from config import LEVEL_FILE_NAMES


# Ghi danh sách record ra file JSONL.
def write_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# Ghi dict/list ra file JSON.
def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Ghi CSV chung để tránh lặp code.
def write_csv(path, rows, fieldnames):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Ghi summary CSV cho toàn bộ evidence packages.
def write_summary_csv(path, packages):
    fieldnames = [
        "package_id",
        "source_ir_id",
        "source_evidence_id",
        "evidence_level",
        "selected_evidence_count",
        "adaptive_k",
        "coverage",
        "coverage_threshold",
        "coverage_status",
        "normalized_entropy",
        "entropy_level",
        "top10_coverage_from_gplus",
        "top20_coverage_from_gplus",
        "selection_method",
    ]

    rows = []
    for package in packages:
        metrics = package.get("selection_metrics") or {}
        audit_trace = package.get("audit_trace") or {}

        rows.append({
            "package_id": package.get("package_id"),
            "source_ir_id": package.get("source_ir_id"),
            "source_evidence_id": package.get("source_evidence_id"),
            "evidence_level": package.get("evidence_level"),
            "selected_evidence_count": metrics.get("selected_evidence_count"),
            "adaptive_k": metrics.get("adaptive_k"),
            "coverage": metrics.get("coverage"),
            "coverage_threshold": metrics.get("coverage_threshold"),
            "coverage_status": metrics.get("coverage_status"),
            "normalized_entropy": metrics.get("normalized_entropy"),
            "entropy_level": metrics.get("entropy_level"),
            "top10_coverage_from_gplus": metrics.get("top10_coverage_from_gplus"),
            "top20_coverage_from_gplus": metrics.get("top20_coverage_from_gplus"),
            "selection_method": audit_trace.get("selection_method"),
        })

    write_csv(path, rows, fieldnames)


# Ghi riêng report cho S3/S4 adaptive selection.
def write_adaptive_report_csv(path, packages):
    fieldnames = [
        "package_id",
        "source_ir_id",
        "evidence_level",
        "adaptive_k",
        "coverage",
        "coverage_threshold",
        "coverage_status",
        "normalized_entropy",
        "entropy_level",
        "concept_group_count",
        "mixed_concept_group_count",
        "grouped_supporting_feature_count",
        "selected_feature_ids",
    ]

    rows = []
    for package in packages:
        if package.get("evidence_level") not in ("S3", "S4"):
            continue

        metrics = package.get("selection_metrics") or {}
        audit_trace = package.get("audit_trace") or {}
        selected_feature_ids = audit_trace.get("selected_feature_ids") or []

        rows.append({
            "package_id": package.get("package_id"),
            "source_ir_id": package.get("source_ir_id"),
            "evidence_level": package.get("evidence_level"),
            "adaptive_k": metrics.get("adaptive_k"),
            "coverage": metrics.get("coverage"),
            "coverage_threshold": metrics.get("coverage_threshold"),
            "coverage_status": metrics.get("coverage_status"),
            "normalized_entropy": metrics.get("normalized_entropy"),
            "entropy_level": metrics.get("entropy_level"),
            "concept_group_count": metrics.get("concept_group_count"),
            "mixed_concept_group_count": metrics.get("mixed_concept_group_count"),
            "grouped_supporting_feature_count": metrics.get("grouped_supporting_feature_count"),
            "selected_feature_ids": "|".join(str(x) for x in selected_feature_ids if x is not None),
        })

    write_csv(path, rows, fieldnames)


# Kiểm tra chất lượng tổng thể của output package.
def build_quality_report(ir_records, packages):
    level_counts = {}

    missing_source_ir = 0
    missing_source_evidence = 0
    missing_policy = 0
    missing_forbidden_rule_ids = 0
    s0_with_evidence = 0
    s3_coverage_below = 0
    s4_coverage_below = 0
    s4_high_entropy = 0
    s4_empty_concept_evidence = 0
    top10_coverage_null = 0
    top20_coverage_null = 0

    for package in packages:
        level = package.get("evidence_level")
        metrics = package.get("selection_metrics") or {}
        constraints = package.get("constraints") or {}

        level_counts[level] = level_counts.get(level, 0) + 1

        if not package.get("source_ir_id"):
            missing_source_ir += 1
        if not package.get("source_evidence_id"):
            missing_source_evidence += 1
        if not package.get("narrative_policy"):
            missing_policy += 1
        if not constraints.get("forbidden_rule_ids"):
            missing_forbidden_rule_ids += 1
        if level == "S0" and package.get("selected_evidence"):
            s0_with_evidence += 1
        if level == "S3" and metrics.get("coverage_status") != "PASSED":
            s3_coverage_below += 1
        if level == "S4" and metrics.get("coverage_status") != "PASSED":
            s4_coverage_below += 1
        if level == "S4" and metrics.get("entropy_level") == "high":
            s4_high_entropy += 1
        if level == "S4" and not package.get("concept_evidence"):
            s4_empty_concept_evidence += 1
        if metrics.get("top10_coverage_from_gplus") is None:
            top10_coverage_null += 1
        if metrics.get("top20_coverage_from_gplus") is None:
            top20_coverage_null += 1

    expected_total = len(ir_records) * 6
    errors = []
    warnings = []

    if len(packages) != expected_total:
        errors.append("Output package count does not equal input_ir_count * 6.")
    if missing_source_ir > 0:
        errors.append("Some packages are missing source_ir_id.")
    if s0_with_evidence > 0:
        errors.append("Some S0 packages contain selected_evidence.")
    if missing_source_evidence > 0:
        warnings.append("Some packages are missing source_evidence_id.")
    if missing_policy > 0:
        warnings.append("Some packages are missing narrative_policy.")
    if missing_forbidden_rule_ids > 0:
        warnings.append("Some packages are missing forbidden_rule_ids.")
    if s3_coverage_below > 0:
        warnings.append("Some S3 packages did not reach coverage target within k_max=10.")
    if s4_coverage_below > 0:
        warnings.append("Some S4 packages did not reach coverage target within k_max=20.")
    if s4_empty_concept_evidence > 0:
        warnings.append("Some S4 packages have empty concept_evidence.")
    if top10_coverage_null > 0:
        warnings.append("Some packages have null top10_coverage_from_gplus.")
    if top20_coverage_null > 0:
        warnings.append("Some packages have null top20_coverage_from_gplus.")

    status = "PASSED"
    if warnings:
        status = "PASSED_WITH_WARNINGS"
    if errors:
        status = "FAILED"

    return {
        "batch": "I0_evidence_exposure_layer",
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_ir_record_count": len(ir_records),
        "expected_package_count": expected_total,
        "output_package_count": len(packages),
        "level_counts": level_counts,
        "missing_source_ir_id_count": missing_source_ir,
        "missing_source_evidence_id_count": missing_source_evidence,
        "missing_narrative_policy_count": missing_policy,
        "missing_forbidden_rule_ids_count": missing_forbidden_rule_ids,
        "s0_with_evidence_count": s0_with_evidence,
        "s3_coverage_below_target_count": s3_coverage_below,
        "s4_coverage_below_target_count": s4_coverage_below,
        "s4_high_entropy_count": s4_high_entropy,
        "s4_empty_concept_evidence_count": s4_empty_concept_evidence,
        "top10_coverage_null_count": top10_coverage_null,
        "top20_coverage_null_count": top20_coverage_null,
        "errors": errors,
        "warnings": warnings,
    }


# Ghi toàn bộ artifact chính, split file, report và manifest.
def write_all_artifacts(packages, ir_records, output_dir, manifest_dir, input_path):
    output_dir = Path(output_dir)
    manifest_dir = Path(manifest_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    main_output = output_dir / "evidence_packages.jsonl"
    summary_output = output_dir / "evidence_package_summary.csv"
    adaptive_output = output_dir / "adaptive_selection_report.csv"
    quality_output = output_dir / "evidence_exposure_quality_report.json"
    manifest_output = manifest_dir / "evidence_exposure_manifest_evaluation.json"

    write_jsonl(main_output, packages)

    for level, file_name in LEVEL_FILE_NAMES.items():
        level_packages = []
        for package in packages:
            if package.get("evidence_level") == level:
                level_packages.append(package)

        write_jsonl(output_dir / file_name, level_packages)

    write_summary_csv(summary_output, packages)
    write_adaptive_report_csv(adaptive_output, packages)

    quality_report = build_quality_report(ir_records, packages)
    write_json(quality_output, quality_report)

    manifest = {
        "batch": "I0_evidence_exposure_layer",
        "status": quality_report.get("status"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(input_path),
        "output_dir": str(output_dir),
        "input_ir_record_count": len(ir_records),
        "output_package_count": len(packages),
        "main_output": str(main_output),
        "split_outputs": {
            level: str(output_dir / file_name)
            for level, file_name in LEVEL_FILE_NAMES.items()
        },
        "summary_output": str(summary_output),
        "adaptive_report_output": str(adaptive_output),
        "quality_report_output": str(quality_output),
    }

    write_json(manifest_output, manifest)

    return quality_report