#!/usr/bin/env python3
"""Build and certify the Freddie 648-row research data mart."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from research.python.data_mart.build import CLAIM_TYPES, build_data_mart, write_data_mart
from research.python.data_mart.load import load_input_data
from research.python.data_mart.validate import validate_data_mart, write_validation_report

from freddie_analysis_common_0021 import (
    file_record,
    sha256,
    prepare_staging,
    promote_directory,
    read_json,
    verify_lock_artifacts,
    write_json,
)

FREDDIE_CLAIM_TYPES = tuple(dict.fromkeys((*CLAIM_TYPES, "causal")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--input-lock", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    protocol = read_json(Path(args.protocol).resolve())
    input_lock_path = Path(args.input_lock).resolve()
    lock = read_json(input_lock_path)
    output_dir = Path(args.output_dir).resolve()

    if lock.get("gate") != "FREDDIE_ANALYSIS_INPUT_LOCK_READY":
        raise ValueError("M21 requires FREDDIE_ANALYSIS_INPUT_LOCK_READY.")
    if lock.get("dataset_id") != protocol.get("dataset_id"):
        raise ValueError("Protocol/input-lock dataset mismatch.")
    if lock.get("analysis_policies", {}).get("provider_execution_allowed") is not False:
        raise ValueError("Provider execution must remain disabled after M20.")

    paths = verify_lock_artifacts(
        root,
        lock,
        [
            "generation_index",
            "evidence_packages",
            "claims_final",
            "validation_results",
            "generation_summaries",
        ],
    )
    input_data = load_input_data({
        "generation_index": paths["generation_index"],
        "evidence_packages": paths["evidence_packages"],
        "final_claims": paths["claims_final"],
        "validation_results": paths["validation_results"],
        "generation_summaries": paths["generation_summaries"],
    })

    observed = lock["observed"]
    expected_counts = {
        "cases": int(observed["canonical_cases"]),
        "models": int(observed["models"]),
        "evidence_levels": int(observed["evidence_conditions"]),
        "evidence_packages": int(observed["evidence_packages"]),
        "generations": int(observed["planned_generations"]),
        "usable_generations": int(observed["usable_generations"]),
        "unusable_generations": int(observed["unusable_generations"]),
        "claims": int(observed["final_claims"]),
        "validation_results": int(observed["validation_results"]),
        "generation_summaries": int(observed["generation_summaries"]),
    }
    expected_strata = {
        str(name): int(protocol["expected_stratum_count_each"])
        for name in protocol["strata"]
    }
    release_context: dict[str, Any] = {
        "release_id": "freddie_sflld_2024_deterministic_v4_measurement",
        "release_status": "READY_WITH_LIMITATIONS",
        "allowed_release_statuses": ["READY", "READY_WITH_LIMITATIONS"],
        "interpretation_scope": (
            "Automated deterministic claim-validation measurement; not human ground truth."
        ),
        "expected_primary_condition": "deterministic_v4",
        "decision": {"primary_condition": "deterministic_v4"},
    }

    observed_claim_types = sorted({str(row.get("claim_type")) for row in input_data["final_claims"]})
    unknown_claim_types = sorted(set(observed_claim_types) - set(FREDDIE_CLAIM_TYPES))
    if unknown_claim_types:
        raise ValueError(f"Unregistered Freddie claim types: {unknown_claim_types}")

    tables = build_data_mart(input_data, claim_types=FREDDIE_CLAIM_TYPES)
    report = validate_data_mart(
        tables,
        input_data,
        expected_counts=expected_counts,
        expected_status_counts={
            str(key): int(value)
            for key, value in observed["validation_status_counts"].items()
        },
        expected_stratum_counts=expected_strata,
        release_context=release_context,
    )

    # Dataset-specific topology checks supplement, rather than weaken, common gates.
    generations = tables["generations"]
    claims = tables["claims"]
    actual_unusable = sorted(generations.loc[~generations["usable"].astype(bool), "generation_id"].astype(str))
    locked_unusable = sorted(
        str(row["generation_id"]) for row in observed["unusable_generation_records"]
    )
    extra_checks = {
        "locked_unusable_identity_match": actual_unusable == locked_unusable,
        "claim_type_registry_complete": not unknown_claim_types,
        "causal_aggregate_column_present": "causal_claim_count" in generations.columns,
        "generation_claim_sum_exact": int(generations["claim_count"].sum()) == len(claims),
        "model_evidence_option_count": int(
            generations[["model_id", "evidence_level"]].drop_duplicates().shape[0]
        ) == 18,
        "planned_generations_per_option": generations.groupby(
            ["model_id", "evidence_level"]
        ).size().eq(36).all(),
    }
    failed_extra = [name for name, passed in extra_checks.items() if not bool(passed)]
    report["freddie_checks"] = {name: bool(value) for name, value in extra_checks.items()}
    report["check_count"] = int(report["check_count"]) + len(extra_checks)
    report["failed_check_count"] = int(report["failed_check_count"]) + len(failed_extra)
    report["passed"] = report["failed_check_count"] == 0
    report["exit_gate"] = "DATA_MART_READY" if report["passed"] else "DATA_MART_INVALID"
    report["dataset_id"] = protocol["dataset_id"]
    report["experiment_id"] = protocol["experiment_id"]
    report["claim_types"] = list(FREDDIE_CLAIM_TYPES)
    if not report["passed"]:
        raise ValueError(
            "Freddie M21 data-mart validation failed: "
            + json.dumps(report, ensure_ascii=False, sort_keys=True)
        )

    staging = prepare_staging(output_dir)
    try:
        write_data_mart(tables, staging)
        write_validation_report(report, staging)
        files: dict[str, Any] = {}
        for path in sorted(p for p in staging.iterdir() if p.is_file()):
            row_count = None
            if path.suffix == ".csv":
                table_name = path.stem
                if table_name in tables:
                    row_count = len(tables[table_name])
            record = file_record(root, path, row_count=row_count)
            record["path"] = str((output_dir / path.name).relative_to(root))
            files[path.name] = record
        manifest = {
            "schema_version": "freddie_data_mart_manifest_v1",
            "dataset_id": protocol["dataset_id"],
            "experiment_id": protocol["experiment_id"],
            "producer": "M21B_0021",
            "parent_analysis_input_lock": file_record(root, input_lock_path),
            "counts": expected_counts,
            "validation_status_counts": observed["validation_status_counts"],
            "claim_types": list(FREDDIE_CLAIM_TYPES),
            "complete_case_count_frozen_upstream": int(observed["complete_case_count"]),
            "files": files,
            "gate": "DATA_MART_READY",
            "freddie_gate": "FREDDIE_M21_DATA_MART_READY",
        }
        write_json(staging / "data_mart_manifest.json", manifest)
        status = promote_directory(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print(
        f"FREDDIE_M21_DATA_MART={status} generations={len(generations)} "
        f"usable={int(generations['usable'].sum())} unusable={int((~generations['usable'].astype(bool)).sum())} "
        f"claims={len(claims)} options=18"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
