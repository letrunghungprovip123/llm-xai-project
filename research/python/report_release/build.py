"""Create report numbers, source index, lineage manifest and readiness gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import pandas as pd

from research.python.common.hashing import sha256_file
from research.python.common.paths import DEFAULT_PATHS
from research.python.common.research_release import (
    load_claim_measurement_release,
)

from .config import (
    ANALYSIS_ROOT,
    CERTIFIED_REPORT_FILES,
    PROJECT_ROOT,
    REQUIRED_GATES,
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def run_git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.stdout.strip()


def source_tree_sha256() -> str:
    """Hash report-relevant source/config/docs independently of Git state."""

    roots = [
        PROJECT_ROOT / "research",
        PROJECT_ROOT / "config" / "research",
        PROJECT_ROOT / "docs" / "research",
        PROJECT_ROOT / "tests" / "research",
    ]
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(
                path
                for path in root.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
            )
    digest = hashlib.sha256()
    for path in sorted(files):
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_gates() -> dict[str, dict[str, Any]]:
    return {
        name: read_json(path)
        for name, (path, _) in REQUIRED_GATES.items()
    }


def build_report_numbers() -> dict[str, Any]:
    metrics = pd.read_csv(
        ANALYSIS_ROOT / "data_mart" / "generation_metrics.csv"
    )
    omnibus = pd.read_csv(
        ANALYSIS_ROOT / "statistical_analysis" / "omnibus_tests.csv"
    )
    paired = pd.read_csv(
        ANALYSIS_ROOT / "statistical_analysis" / "paired_tests.csv"
    )
    sensitivity = pd.read_csv(
        ANALYSIS_ROOT / "statistical_analysis" / "sensitivity_summary.csv"
    )
    recommendations = pd.read_csv(
        ANALYSIS_ROOT / "decision_support" / "recommendations.csv"
    )
    validator_tests = pd.read_csv(
        ANALYSIS_ROOT
        / "validator_sensitivity"
        / "validator_sensitivity_tests.csv"
    )

    supported = int(metrics["supported_count"].sum())
    unsupported = int(metrics["unsupported_count"].sum())
    contradicted = int(metrics["contradicted_count"].sum())
    not_verifiable = int(metrics["not_verifiable_count"].sum())
    not_applicable = int(metrics["not_applicable_count"].sum())
    resolved = supported + unsupported + contradicted
    applicable = resolved + not_verifiable

    primary_recommendations = recommendations.loc[
        recommendations["recommendation_role"].eq("PRIMARY")
    ]

    return {
        "schema_version": "report_numbers_v1",
        "claim_measurement_release_id": (
            load_claim_measurement_release()["release_id"]
        ),
        "denominators": {
            "planned_llm_generations": int(len(metrics)),
            "usable_llm_generations": int(metrics["usable"].sum()),
            "unusable_llm_generations": int(metrics["is_unusable"].sum()),
            "final_atomic_claims": int(metrics["claim_count"].sum()),
            "resolved_claims": resolved,
            "applicable_claims": applicable,
        },
        "claim_status_counts": {
            "SUPPORTED": supported,
            "NOT_VERIFIABLE": not_verifiable,
            "UNSUPPORTED": unsupported,
            "CONTRADICTED": contradicted,
            "NOT_APPLICABLE": not_applicable,
        },
        "primary_metrics": {
            "mean_end_to_end_operational_faithfulness": float(
                metrics["end_to_end_faithfulness_yield"].mean()
            ),
            "usability_rate": float(metrics["usable"].mean()),
            "micro_resolved_faithfulness": supported / resolved,
            "micro_verifiability": resolved / applicable,
            "micro_conservative_faithfulness": supported / applicable,
        },
        "primary_omnibus_tests": omnibus.to_dict(orient="records"),
        "primary_adjusted_significant_pair_count": int(
            paired["significant_adjusted"].sum()
        ),
        "primary_planned_pair_count": int(len(paired)),
        "complete_case_sensitivity": sensitivity.to_dict(orient="records"),
        "validator_sensitivity_significant_test_count": int(
            validator_tests["significant_adjusted"].sum()
        ),
        "recommendations": primary_recommendations[
            [
                "scenario_id",
                "option_id",
                "utility_score",
                "tested_comparator_count",
                "significant_disadvantage_count",
                "untested_comparator_count",
            ]
        ].to_dict(orient="records"),
        "reporting_scope": (
            "operational faithfulness under the frozen project ontology "
            "and deterministic validator; not human ground truth"
        ),
    }


def build_source_index() -> pd.DataFrame:
    rows = [
        {
            "report_item": "primary_endpoint",
            "official_name": "End-to-end operational faithfulness yield",
            "source_path": "analysis/data_mart/generation_metrics.csv",
            "source_field": "end_to_end_faithfulness_yield",
            "aggregation": "macro mean",
            "population_denominator": "648 planned LLM generations",
        },
        {
            "report_item": "conditional_faithfulness",
            "official_name": "Conservative faithfulness",
            "source_path": "analysis/data_mart/generation_metrics.csv",
            "source_field": "conservative_faithfulness",
            "aggregation": "micro ratio or generation distribution",
            "population_denominator": "usable rows with applicable claims",
        },
        {
            "report_item": "primary_omnibus",
            "official_name": "Model, evidence and interaction effects",
            "source_path": "analysis/statistical_analysis/omnibus_tests.csv",
            "source_field": "p_value_greenhouse_geisser",
            "aggregation": "case-level repeated measures",
            "population_denominator": "36 canonical cases; 648 cells",
        },
        {
            "report_item": "conditional_pair_tests",
            "official_name": "Conditional semantic paired sensitivity",
            "source_path": "analysis/statistical_analysis/conditional_paired_tests.csv",
            "source_field": "adjusted_p_value",
            "aggregation": "case-paired Wilcoxon with Holm correction",
            "population_denominator": "observed complete pairs shown per row",
        },
        {
            "report_item": "unusable_failures",
            "official_name": "Structured pipeline failures",
            "source_path": "analysis/statistical_analysis/unusable_generations.csv",
            "source_field": "generation_id",
            "aggregation": "count and failure breakdown",
            "population_denominator": "10 unusable of 648 planned",
        },
        {
            "report_item": "validator_sensitivity",
            "official_name": "Candidate versus V4 measurement sensitivity",
            "source_path": "analysis/validator_sensitivity/validator_sensitivity_tests.csv",
            "source_field": "adjusted_p_value",
            "aggregation": "case-level aggregated paired tests",
            "population_denominator": "36 canonical cases",
        },
        {
            "report_item": "decision_recommendations",
            "official_name": "Scenario utility recommendations",
            "source_path": "analysis/decision_support/recommendations.csv",
            "source_field": "utility_score",
            "aggregation": "preference-based decision score",
            "population_denominator": "18 model-evidence options",
        },
    ]
    return pd.DataFrame(rows)


def build_manifest(gates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    files = []
    for path in CERTIFIED_REPORT_FILES:
        files.append(
            {
                "path": path.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": sha256_file(path),
                "byte_count": path.stat().st_size,
            }
        )
    return {
        "schema_version": "thesis_report_release_manifest_v1",
        "release_id": "thesis_report_v1",
        "source_commit": run_git("rev-parse", "HEAD"),
        "source_tree_sha256": source_tree_sha256(),
        "git_branch": run_git("branch", "--show-current"),
        "git_status_before_release": run_git("status", "--porcelain"),
        "claim_measurement_release": load_claim_measurement_release(),
        "gate_statuses": {
            name: {
                "passed": report.get("passed"),
                "failed_check_count": report.get("failed_check_count"),
                "exit_gate": report.get("exit_gate"),
            }
            for name, report in gates.items()
        },
        "certified_report_files": files,
        "report_contracts": [
            "config/research/analysis_plan_v1.json",
            "docs/research/analysis_plan_v1.md",
            "docs/research/reporting_contract_v1.md",
        ],
    }


def validate_readiness(
    gates: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
    report_numbers: dict[str, Any],
    require_clean_git: bool = True,
) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}

    for name, (_, expected_gate) in REQUIRED_GATES.items():
        observed = gates[name].get("exit_gate")
        passed = (
            gates[name].get("passed") is True
            and gates[name].get("failed_check_count") == 0
            and observed == expected_gate
        )
        checks[f"gate_{name}"] = {
            "expected": expected_gate,
            "observed": observed,
            "passed": passed,
        }

    denominators = report_numbers["denominators"]
    expected_counts = {
        "planned_llm_generations": 648,
        "usable_llm_generations": 638,
        "unusable_llm_generations": 10,
        "final_atomic_claims": 14667,
    }
    for name, expected in expected_counts.items():
        observed = denominators[name]
        checks[f"count_{name}"] = {
            "expected": expected,
            "observed": observed,
            "passed": observed == expected,
        }

    status = manifest["claim_measurement_release"]["release_status"]
    checks["claim_release_ready"] = {
        "expected": ["READY", "READY_WITH_LIMITATIONS"],
        "observed": status,
        "passed": status in {"READY", "READY_WITH_LIMITATIONS"},
    }

    git_status = manifest["git_status_before_release"]
    checks["clean_git_snapshot"] = {
        "expected": "clean" if require_clean_git else "clean_or_preview",
        "observed": "clean" if not git_status else git_status,
        "passed": (not git_status) or (not require_clean_git),
    }

    missing_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in CERTIFIED_REPORT_FILES
        if not path.is_file()
    ]
    checks["certified_report_files_present"] = {
        "expected": [],
        "observed": missing_files,
        "passed": not missing_files,
    }

    failed = sum(not check["passed"] for check in checks.values())
    return {
        "schema_version": "report_readiness_validation_v1",
        "check_count": len(checks),
        "failed_check_count": failed,
        "passed": failed == 0,
        "exit_gate": (
            "REPORT_WRITING_READY"
            if failed == 0
            else "REPORT_WRITING_NOT_READY"
        ),
        "checks": checks,
    }
