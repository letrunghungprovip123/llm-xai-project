import csv
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from config import (
    BUILDER_VERSION,
    EVIDENCE_PACKAGE_SCHEMA_VERSION,
    FORBIDDEN_PROMPT_KEYS,
    LEVEL_FILE_NAMES,
    S1_TOP_K,
    S2_TOP_K,
    S3_COVERAGE_THRESHOLD,
    S3_K_MIN,
    S3_K_MAX,
    S4_COVERAGE_THRESHOLD,
    S4_K_MIN,
    S4_K_MAX,
)


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


# Tính SHA-256 cho text ổn định.
def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# Tính SHA-256 cho artifact để khóa input/output của thí nghiệm.
def sha256_file(path):
    path = Path(path)
    if not path.exists():
        return None

    digest = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)

    return digest.hexdigest()


# Lấy git commit nếu code đang nằm trong Git repository.
def get_git_commit_hash():
    env_value = os.getenv("GIT_COMMIT_HASH")
    if env_value:
        return env_value

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


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
        "coverage_gap",
        "is_compacted",
        "reached_k_max",
        "normalized_entropy",
        "entropy_level",
        "concept_group_count",
        "unique_concept_count",
        "mixed_concept_group_count",
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
            "coverage_gap": metrics.get("coverage_gap"),
            "is_compacted": metrics.get("is_compacted"),
            "reached_k_max": metrics.get("reached_k_max"),
            "normalized_entropy": metrics.get("normalized_entropy"),
            "entropy_level": metrics.get("entropy_level"),
            "concept_group_count": metrics.get("concept_group_count"),
            "unique_concept_count": metrics.get("unique_concept_count"),
            "mixed_concept_group_count": metrics.get("mixed_concept_group_count"),
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
        "coverage_gap",
        "reached_k_max",
        "normalized_entropy",
        "entropy_level",
        "concept_group_count",
        "unique_concept_count",
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
            "coverage_gap": metrics.get("coverage_gap"),
            "reached_k_max": metrics.get("reached_k_max"),
            "normalized_entropy": metrics.get("normalized_entropy"),
            "entropy_level": metrics.get("entropy_level"),
            "concept_group_count": metrics.get("concept_group_count"),
            "unique_concept_count": metrics.get("unique_concept_count"),
            "mixed_concept_group_count": metrics.get("mixed_concept_group_count"),
            "grouped_supporting_feature_count": metrics.get("grouped_supporting_feature_count"),
            "selected_feature_ids": "|".join(str(x) for x in selected_feature_ids if x is not None),
        })

    write_csv(path, rows, fieldnames)


# Tìm key không được phép xuất hiện trong prompt_payload.
def find_forbidden_prompt_keys(value, path="prompt_payload"):
    findings = []

    if isinstance(value, dict):
        for key, item in value.items():
            current_path = f"{path}.{key}"

            if key in FORBIDDEN_PROMPT_KEYS:
                findings.append(current_path)

            findings.extend(find_forbidden_prompt_keys(item, current_path))

    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(
                find_forbidden_prompt_keys(item, f"{path}[{index}]")
            )

    return findings


# Lấy ordered feature IDs của package.
def get_selected_feature_ids(package):
    result = []

    for item in package.get("selected_evidence") or []:
        if isinstance(item, dict):
            result.append(item.get("feature_id"))

    return result


# Lấy SHAP signature để so S1-S2 và S4-S5.
def get_selected_shap_signature(package):
    result = []

    for item in package.get("selected_evidence") or []:
        if not isinstance(item, dict):
            continue

        result.append((
            item.get("feature_id"),
            item.get("rank"),
            item.get("shap_value"),
            item.get("abs_shap_value"),
            item.get("direction"),
        ))

    return result


# Lấy concept signature chỉ từ feature đã chọn.
def get_concept_signature(package):
    result = []

    for group in package.get("concept_evidence") or []:
        if not isinstance(group, dict):
            continue

        result.append((
            group.get("concept"),
            group.get("direction"),
            tuple(group.get("selected_feature_ids") or []),
        ))

    return result


# Kiểm tra chất lượng tổng thể của output package.
def build_quality_report(ir_records, packages):
    level_counts = {}
    packages_by_ir = {}
    package_ids = []

    missing_source_ir = 0
    missing_source_evidence = 0
    missing_policy = 0
    missing_forbidden_rule_ids = 0
    missing_prompt_payload = 0
    prompt_leakage_findings = []
    s0_with_evidence = 0
    s0_invalid_claim_policy = 0
    s1_s2_feature_order_mismatch = 0
    s1_s2_shap_mismatch = 0
    s3_coverage_below = 0
    s4_coverage_below = 0
    s4_high_entropy = 0
    s4_empty_concept_evidence = 0
    s4_unselected_concept_feature_count = 0
    s4_grouping_contract_error_count = 0
    s4_s5_evidence_mismatch = 0
    s4_s5_concept_mismatch = 0
    top10_coverage_null = 0
    top20_coverage_null = 0
    semantic_fallback_count = 0
    semantic_item_count = 0

    for package in packages:
        level = package.get("evidence_level")
        source_ir_id = package.get("source_ir_id")
        metrics = package.get("selection_metrics") or {}
        constraints = package.get("constraints") or {}
        prompt_payload = package.get("prompt_payload")

        level_counts[level] = level_counts.get(level, 0) + 1
        package_ids.append(package.get("package_id"))

        if source_ir_id not in packages_by_ir:
            packages_by_ir[source_ir_id] = {}
        packages_by_ir[source_ir_id][level] = package

        if not source_ir_id:
            missing_source_ir += 1
        if not package.get("source_evidence_id"):
            missing_source_evidence += 1
        if not package.get("narrative_policy"):
            missing_policy += 1
        if not constraints.get("forbidden_rule_ids"):
            missing_forbidden_rule_ids += 1
        if not isinstance(prompt_payload, dict) or not prompt_payload:
            missing_prompt_payload += 1
        else:
            for finding in find_forbidden_prompt_keys(prompt_payload):
                prompt_leakage_findings.append({
                    "package_id": package.get("package_id"),
                    "path": finding,
                })

        if level == "S0":
            if package.get("selected_evidence"):
                s0_with_evidence += 1

            claim_policy = constraints.get("claim_policy") or {}
            invalid_keys = (
                "allow_feature_claim",
                "allow_concept_claim",
                "allow_direction_claim",
                "allow_magnitude_claim",
                "allow_causal_claim",
                "allow_financial_advice",
                "allow_true_label_claim",
            )

            if any(claim_policy.get(key) is True for key in invalid_keys):
                s0_invalid_claim_policy += 1

        if level == "S2":
            for item in package.get("selected_evidence") or []:
                semantic_item_count += 1
                if item.get("display_name_source") == "fallback":
                    semantic_fallback_count += 1

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

    expected_levels = set(LEVEL_FILE_NAMES.keys())
    missing_case_level_count = 0

    for level_map in packages_by_ir.values():
        missing_case_level_count += len(expected_levels - set(level_map.keys()))

        s1 = level_map.get("S1")
        s2 = level_map.get("S2")
        s4 = level_map.get("S4")
        s5 = level_map.get("S5")

        if s1 and s2:
            if get_selected_feature_ids(s1) != get_selected_feature_ids(s2):
                s1_s2_feature_order_mismatch += 1
            if get_selected_shap_signature(s1) != get_selected_shap_signature(s2):
                s1_s2_shap_mismatch += 1

        if s4:
            selected_ids = set(get_selected_feature_ids(s4))
            seen_group_keys = set()
            representative_count = 0

            for group in s4.get("concept_evidence") or []:
                if not isinstance(group, dict):
                    s4_grouping_contract_error_count += 1
                    continue

                group_ids = set(group.get("selected_feature_ids") or [])
                s4_unselected_concept_feature_count += len(group_ids - selected_ids)

                group_key = (group.get("concept"), group.get("direction"))
                if group_key in seen_group_keys:
                    s4_grouping_contract_error_count += 1
                seen_group_keys.add(group_key)

                if isinstance(group.get("representative_feature"), dict):
                    representative_count += 1
                else:
                    s4_grouping_contract_error_count += 1

            if representative_count != len(s4.get("concept_evidence") or []):
                s4_grouping_contract_error_count += 1

        if s4 and s5:
            if get_selected_shap_signature(s4) != get_selected_shap_signature(s5):
                s4_s5_evidence_mismatch += 1
            if get_concept_signature(s4) != get_concept_signature(s5):
                s4_s5_concept_mismatch += 1

    duplicate_generation_count = len(package_ids) - len(set(package_ids))
    expected_total = len(ir_records) * len(LEVEL_FILE_NAMES)
    errors = []
    warnings = []

    if len(packages) != expected_total:
        errors.append("Output package count does not equal input_ir_count * 6.")
    if duplicate_generation_count > 0:
        errors.append("Some package_id values are duplicated.")
    if missing_case_level_count > 0:
        errors.append("Some source IR cases do not have all S0-S5 levels.")
    if missing_source_ir > 0:
        errors.append("Some packages are missing source_ir_id.")
    if missing_prompt_payload > 0:
        errors.append("Some packages are missing prompt_payload.")
    if prompt_leakage_findings:
        errors.append("Some prompt_payload objects contain forbidden evaluation metadata.")
    if s0_with_evidence > 0:
        errors.append("Some S0 packages contain selected_evidence.")
    if s0_invalid_claim_policy > 0:
        errors.append("Some S0 packages allow feature, concept, direction, magnitude, causal, advice, or true-label claims.")
    if s1_s2_feature_order_mismatch > 0:
        errors.append("S1 and S2 do not use the exact same ordered feature IDs for some cases.")
    if s1_s2_shap_mismatch > 0:
        errors.append("S1 and S2 do not preserve the exact same SHAP evidence for some cases.")
    if s4_unselected_concept_feature_count > 0:
        errors.append("Some S4 concept groups expose feature IDs outside selected_evidence.")
    if s4_grouping_contract_error_count > 0:
        errors.append("Some S4 concept groups do not follow the concept + direction grouping contract.")
    if s4_s5_evidence_mismatch > 0:
        errors.append("S4 and S5 do not use the exact same selected evidence for some cases.")
    if s4_s5_concept_mismatch > 0:
        errors.append("S4 and S5 do not use the exact same concept evidence for some cases.")

    if missing_source_evidence > 0:
        warnings.append("Some packages are missing source_evidence_id.")
    if missing_policy > 0:
        warnings.append("Some packages are missing narrative_policy.")
    if missing_forbidden_rule_ids > 0:
        warnings.append("Some packages are missing forbidden_rule_ids.")
    if s3_coverage_below > 0:
        warnings.append(f"Some S3 packages did not reach coverage target within k_max={S3_K_MAX}.")
    if s4_coverage_below > 0:
        warnings.append(f"Some S4 packages did not reach coverage target within k_max={S4_K_MAX}.")
    if s4_empty_concept_evidence > 0:
        warnings.append("Some S4 packages have empty concept_evidence.")
    if top10_coverage_null > 0:
        warnings.append("Some packages have null top10_coverage_from_gplus.")
    if top20_coverage_null > 0:
        warnings.append("Some packages have null top20_coverage_from_gplus.")
    if semantic_fallback_count > 0:
        warnings.append("Some S2 semantic evidence items still use fallback display names.")

    status = "PASSED"
    if warnings:
        status = "PASSED_WITH_WARNINGS"
    if errors:
        status = "FAILED"

    return {
        "batch": "I0_evidence_exposure_layer",
        "builder_version": BUILDER_VERSION,
        "evidence_package_schema_version": EVIDENCE_PACKAGE_SCHEMA_VERSION,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_ir_record_count": len(ir_records),
        "expected_package_count": expected_total,
        "output_package_count": len(packages),
        "level_counts": level_counts,
        "duplicate_package_id_count": duplicate_generation_count,
        "missing_case_level_count": missing_case_level_count,
        "missing_source_ir_id_count": missing_source_ir,
        "missing_source_evidence_id_count": missing_source_evidence,
        "missing_narrative_policy_count": missing_policy,
        "missing_forbidden_rule_ids_count": missing_forbidden_rule_ids,
        "missing_prompt_payload_count": missing_prompt_payload,
        "prompt_leakage_finding_count": len(prompt_leakage_findings),
        "prompt_leakage_findings": prompt_leakage_findings[:100],
        "s0_with_evidence_count": s0_with_evidence,
        "s0_invalid_claim_policy_count": s0_invalid_claim_policy,
        "s1_s2_feature_order_mismatch_count": s1_s2_feature_order_mismatch,
        "s1_s2_shap_mismatch_count": s1_s2_shap_mismatch,
        "s3_coverage_below_target_count": s3_coverage_below,
        "s4_coverage_below_target_count": s4_coverage_below,
        "s4_high_entropy_count": s4_high_entropy,
        "s4_empty_concept_evidence_count": s4_empty_concept_evidence,
        "s4_unselected_concept_feature_count": s4_unselected_concept_feature_count,
        "s4_grouping_contract_error_count": s4_grouping_contract_error_count,
        "s4_s5_evidence_mismatch_count": s4_s5_evidence_mismatch,
        "s4_s5_concept_mismatch_count": s4_s5_concept_mismatch,
        "semantic_item_count": semantic_item_count,
        "semantic_fallback_count": semantic_fallback_count,
        "top10_coverage_null_count": top10_coverage_null,
        "top20_coverage_null_count": top20_coverage_null,
        "errors": errors,
        "warnings": warnings,
    }


# Ghi toàn bộ artifact chính, split file, report và manifest.
def write_all_artifacts(packages, ir_records, output_dir, manifest_dir, input_path, run_mode="evaluation"):
    output_dir = Path(output_dir)
    manifest_dir = Path(manifest_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    main_output = output_dir / "evidence_packages.jsonl"
    summary_output = output_dir / "evidence_package_summary.csv"
    adaptive_output = output_dir / "adaptive_selection_report.csv"
    quality_output = output_dir / "evidence_exposure_quality_report.json"
    manifest_output = manifest_dir / f"evidence_exposure_manifest_{run_mode}.json"

    write_jsonl(main_output, packages)

    split_outputs = {}

    for level, file_name in LEVEL_FILE_NAMES.items():
        level_packages = []
        for package in packages:
            if package.get("evidence_level") == level:
                level_packages.append(package)

        level_output = output_dir / file_name
        write_jsonl(level_output, level_packages)
        split_outputs[level] = {
            "path": str(level_output),
            "sha256": sha256_file(level_output),
            "record_count": len(level_packages),
        }

    write_summary_csv(summary_output, packages)
    write_adaptive_report_csv(adaptive_output, packages)

    quality_report = build_quality_report(ir_records, packages)
    write_json(quality_output, quality_report)

    manifest = {
        "batch": "I0_evidence_exposure_layer",
        "builder_version": BUILDER_VERSION,
        "evidence_package_schema_version": EVIDENCE_PACKAGE_SCHEMA_VERSION,
        "status": quality_report.get("status"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_mode": run_mode,
        "git_commit_hash": get_git_commit_hash(),
        "input": {
            "path": str(input_path),
            "sha256": sha256_file(input_path),
            "ir_record_count": len(ir_records),
            "source_ir_ids_sha256": sha256_text(
                "\n".join(
                    sorted(
                        str(item.get("ir_id") or item.get("source_ir_id"))
                        for item in ir_records
                        if item.get("ir_id") or item.get("source_ir_id")
                    )
                )
            ),
        },
        "output_dir": str(output_dir),
        "output_package_count": len(packages),
        "main_output": {
            "path": str(main_output),
            "sha256": sha256_file(main_output),
        },
        "split_outputs": split_outputs,
        "summary_output": {
            "path": str(summary_output),
            "sha256": sha256_file(summary_output),
        },
        "adaptive_report_output": {
            "path": str(adaptive_output),
            "sha256": sha256_file(adaptive_output),
        },
        "quality_report_output": {
            "path": str(quality_output),
            "sha256": sha256_file(quality_output),
        },
        "selection_config": {
            "S1": {
                "method": "fixed_raw_shap_topk",
                "top_k": S1_TOP_K,
            },
            "S2": {
                "method": "semantic_enrichment_of_exact_s1_feature_set",
                "top_k": S2_TOP_K,
            },
            "S3": {
                "method": "adaptive_shap_coverage",
                "coverage_threshold": S3_COVERAGE_THRESHOLD,
                "k_min": S3_K_MIN,
                "k_max": S3_K_MAX,
            },
            "S4": {
                "method": "adaptive_coverage_entropy_concept_direction_grouping",
                "coverage_threshold": S4_COVERAGE_THRESHOLD,
                "k_min": S4_K_MIN,
                "k_max": S4_K_MAX,
            },
            "S5": {
                "method": "same_s4_evidence_with_backend_overguidance",
            },
        },
        "prompt_contract": {
            "prompt_source_field": "prompt_payload",
            "ground_truth_allowed_in_prompt": False,
            "forbidden_prompt_keys": sorted(FORBIDDEN_PROMPT_KEYS),
        },
    }

    write_json(manifest_output, manifest)

    return quality_report
