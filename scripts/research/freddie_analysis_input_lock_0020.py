#!/usr/bin/env python3
"""Freeze M20 outputs and the canonical usability topology before M21-M23."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = {
    "SUPPORTED",
    "UNSUPPORTED",
    "CONTRADICTED",
    "NOT_VERIFIABLE",
    "NOT_APPLICABLE",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_number}")
        rows.append(value)
    if not rows:
        raise ValueError(f"Required artifact is empty: {path}")
    return rows


def git_value(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()




def artifact(root: Path, path: Path, record_count: int | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    try:
        display = str(resolved.relative_to(root.resolve()))
    except ValueError:
        display = str(resolved)
    result: dict[str, Any] = {
        "path": display,
        "sha256": sha256(resolved),
        "byte_count": resolved.stat().st_size,
    }
    if record_count is not None:
        result["record_count"] = record_count
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--generation-index", required=True)
    parser.add_argument("--evidence-packages", required=True)
    parser.add_argument("--claims", required=True)
    parser.add_argument("--validation-results", required=True)
    parser.add_argument("--generation-summaries", required=True)
    parser.add_argument("--validation-manifest", required=True)
    parser.add_argument("--m20-input-lock", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    protocol_path = Path(args.protocol).resolve()
    generation_path = Path(args.generation_index).resolve()
    evidence_path = Path(args.evidence_packages).resolve()
    claims_path = Path(args.claims).resolve()
    results_path = Path(args.validation_results).resolve()
    summaries_path = Path(args.generation_summaries).resolve()
    validation_manifest_path = Path(args.validation_manifest).resolve()
    m20_lock_path = Path(args.m20_input_lock).resolve()
    output = Path(args.output).resolve()

    protocol = read_json(protocol_path)
    expected = protocol["population"]
    generation_rows = read_jsonl(generation_path)
    evidence_rows = read_jsonl(evidence_path)
    claims = read_jsonl(claims_path)
    results = read_jsonl(results_path)
    summaries = read_jsonl(summaries_path)
    _ = read_json(validation_manifest_path)
    _ = read_json(m20_lock_path)

    assert len(generation_rows) == int(expected["planned_generations"])
    assert len(evidence_rows) == int(expected["evidence_packages"])
    assert len(summaries) == int(expected["planned_generations"])

    generation_ids = [str(row["generation_id"]) for row in generation_rows]
    assert len(generation_ids) == len(set(generation_ids))
    case_ids = {str(row["case_id"]) for row in generation_rows}
    model_ids = {str(row["model_id"]) for row in generation_rows}
    evidence_levels = {str(row["evidence_level"]) for row in generation_rows}
    assert len(case_ids) == int(expected["canonical_cases"])
    assert len(model_ids) == int(expected["models"])
    assert len(evidence_levels) == int(expected["evidence_conditions"])

    claim_ids = [str(row["claim_id"]) for row in claims]
    result_ids = [str(row["claim_id"]) for row in results]
    assert len(claim_ids) == len(set(claim_ids))
    assert len(result_ids) == len(set(result_ids))
    assert set(claim_ids) == set(result_ids)
    assert len(claims) == len(results)

    status_counts: Counter[str] = Counter()
    for result in results:
        assert result.get("execution_status") == "SUCCESS", result.get("claim_id")
        status = str(result.get("validation_status"))
        assert status in ALLOWED_STATUSES, status
        status_counts[status] += 1
    assert sum(status_counts.values()) == len(results)

    usability_by_case: dict[str, list[bool]] = defaultdict(list)
    unusable: list[dict[str, Any]] = []
    usable_count = 0
    for row in generation_rows:
        usable = row.get("usable") is True
        usability_by_case[str(row["case_id"])].append(usable)
        if usable:
            usable_count += 1
        else:
            unusable.append(
                {
                    "generation_id": str(row["generation_id"]),
                    "case_id": str(row["case_id"]),
                    "model_id": str(row["model_id"]),
                    "evidence_level": str(row["evidence_level"]),
                    "repeat_id": row.get("repeat_id"),
                    "runtime_status": row.get("runtime_status"),
                    "finish_reason": row.get("finish_reason"),
                    "truncated_response": row.get("truncated_response"),
                    "schema_valid": row.get("schema_valid"),
                    "usability_reason_codes": row.get("usability_reason_codes", []),
                }
            )

    unusable.sort(key=lambda row: row["generation_id"])
    complete_cases = sorted(
        case_id
        for case_id, flags in usability_by_case.items()
        if len(flags) == int(expected["conditions_per_case"]) and all(flags)
    )
    assert usable_count + len(unusable) == len(generation_rows)

    # Freeze exact source bytes relevant to M21-M23.  This supplements git HEAD
    # when patches 0014-0019 are still uncommitted on the user's branch.
    source_paths = [
        root / "research/python/data_mart/build.py",
        root / "research/python/data_mart/validate.py",
        root / "research/python/data_mart/case_metadata.py",
        root / "research/python/metric_engineering/quality.py",
        root / "research/python/metric_engineering/validate.py",
        root / "research/python/statistical_analysis/inference.py",
        root / "research/python/statistical_analysis/validate.py",
    ]

    lock: dict[str, Any] = {
        "schema_version": "freddie_analysis_input_lock_v1",
        "dataset_id": protocol["dataset_id"],
        "experiment_id": protocol["experiment_id"],
        "protocol": artifact(root, protocol_path),
        "source": {
            "git_head": git_value(root, "rev-parse", "HEAD"),
            "identity_strategy": "git_head_plus_explicit_relevant_file_hashes",
            "relevant_files": {
                str(path.relative_to(root)): artifact(root, path)
                for path in source_paths
            },
        },
        "artifacts": {
            "generation_index": artifact(root, generation_path, len(generation_rows)),
            "evidence_packages": artifact(root, evidence_path, len(evidence_rows)),
            "claims_final": artifact(root, claims_path, len(claims)),
            "validation_results": artifact(root, results_path, len(results)),
            "generation_summaries": artifact(root, summaries_path, len(summaries)),
            "validation_manifest": artifact(root, validation_manifest_path),
            "m20_input_lock": artifact(root, m20_lock_path),
        },
        "observed": {
            "planned_generations": len(generation_rows),
            "usable_generations": usable_count,
            "unusable_generations": len(unusable),
            "canonical_cases": len(case_ids),
            "models": len(model_ids),
            "evidence_conditions": len(evidence_levels),
            "evidence_packages": len(evidence_rows),
            "final_claims": len(claims),
            "validation_results": len(results),
            "generation_summaries": len(summaries),
            "validation_status_counts": dict(sorted(status_counts.items())),
            "complete_case_count": len(complete_cases),
            "complete_case_ids": complete_cases,
            "unusable_generation_records": unusable,
            "unusable_generation_identity_sha256": hashlib.sha256(
                json.dumps(unusable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        },
        "analysis_policies": {
            "primary_metric": protocol["primary_endpoint"]["metric_id"],
            "unusable_primary_value": protocol["primary_endpoint"]["unusable_value"],
            "conditional_unusable_handling": protocol["conditional_endpoints"]["unusable_handling"],
            "monetary_cost_comparison_ready": protocol["cost_policy"]["monetary_cost_comparison_ready"],
            "provider_execution_allowed": protocol["provider_execution_allowed"],
        },
        "gate": "FREDDIE_ANALYSIS_INPUT_LOCK_READY",
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output.exists():
        if output.read_text(encoding="utf-8") == encoded:
            print("FREDDIE_M21A_ANALYSIS_INPUT_LOCK=ALREADY_CERTIFIED")
            return 0
        raise SystemExit(f"Refusing to overwrite different analysis input lock: {output}")
    output.write_text(encoded, encoding="utf-8")
    print(
        "FREDDIE_M21A_ANALYSIS_INPUT_LOCK=PASS "
        f"planned={len(generation_rows)} usable={usable_count} unusable={len(unusable)} "
        f"claims={len(claims)} complete_cases={len(complete_cases)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
