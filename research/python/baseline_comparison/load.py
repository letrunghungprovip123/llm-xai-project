"""Load and gate the frozen inputs for Template Baseline analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from research.python.common.research_release import (
    verify_report_release_manifest,
)

from .config import (
    CASES_PATH,
    CLAIM_RELEASE_PATH,
    EVIDENCE_ITEMS_PATH,
    EVIDENCE_LEVELS_PATH,
    EVIDENCE_PACKAGES_PATH,
    LLM_GENERATIONS_PATH,
    LLM_GENERATION_METRICS_PATH,
    MODELS_PATH,
    PARENT_GATE,
    REPORT_MANIFEST_PATH,
    REPORT_READINESS_PATH,
    RQ_CONTRACT_PATH,
    TEMPLATE_INDEX_PATH,
)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path, low_memory=False)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise ValueError(
                    f"Expected JSON object at {path}:{line_number}."
                )
            records.append(value)
    if not records:
        raise ValueError(f"Required JSONL is empty: {path}")
    return records


def require_parent_release_ready(report: dict[str, Any]) -> None:
    if not (
        report.get("passed") is True
        and report.get("failed_check_count") == 0
        and report.get("exit_gate") == PARENT_GATE
    ):
        raise ValueError(
            "Template Baseline analysis requires the frozen "
            f"{PARENT_GATE} parent release."
        )


def require_rq6_contract(contract: dict[str, Any]) -> None:
    questions = contract.get("research_questions", [])
    rq6 = next(
        (item for item in questions if item.get("rq_id") == "RQ6"),
        None,
    )
    if rq6 is None:
        raise ValueError("RQ6 is missing from the visualization contract.")
    if rq6.get("status") != "ACTIVE_AFTER_BASELINE_COMPARISON_READY":
        raise ValueError("RQ6 status is not frozen for baseline activation.")


def load_baseline_inputs() -> dict[str, Any]:
    report_readiness = read_json(REPORT_READINESS_PATH)
    require_parent_release_ready(report_readiness)
    report_manifest = read_json(REPORT_MANIFEST_PATH)
    verified_report_paths = verify_report_release_manifest(report_manifest)
    rq_contract = read_json(RQ_CONTRACT_PATH)
    require_rq6_contract(rq_contract)
    return {
        "template_records": read_jsonl(TEMPLATE_INDEX_PATH),
        "cases": read_csv(CASES_PATH),
        "evidence_packages": read_csv(EVIDENCE_PACKAGES_PATH),
        "evidence_items": read_csv(EVIDENCE_ITEMS_PATH),
        "llm_generations": read_csv(LLM_GENERATIONS_PATH),
        "llm_generation_metrics": read_csv(LLM_GENERATION_METRICS_PATH),
        "models": read_csv(MODELS_PATH),
        "evidence_levels": read_csv(EVIDENCE_LEVELS_PATH),
        "report_readiness": report_readiness,
        "report_manifest": report_manifest,
        "verified_report_paths": verified_report_paths,
        "claim_release": read_json(CLAIM_RELEASE_PATH),
        "rq_contract": rq_contract,
    }
