"""Build visualization v2 presentation marts from certified sources."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from research.python.visualization.build import build_visualization_outputs

from .config import (
    MANIFEST_PATH,
    OUTPUT_DIR,
    OUTPUT_PATHS,
    PROJECT_ROOT,
    VALIDATION_PATH,
    VISUALIZATION_VERSION,
)
from .prepare_research import (
    build_case_heterogeneity_summary,
    build_certified_report_numbers,
    build_evidence_design_summary,
    build_evidence_utilization_summary,
    build_metric_visibility_registry,
    build_narrative_structure_summary,
    build_release_metadata,
    build_rq_registry,
)


def upgrade_legacy_output(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    if "visualization_version" in output.columns:
        output["visualization_version"] = VISUALIZATION_VERSION
    else:
        output.insert(0, "visualization_version", VISUALIZATION_VERSION)
    for column in output.columns:
        if "evidence_label" in column:
            output[column] = output[column].replace(
                {"Prediction-only baseline": "Prediction-only control"}
            )
    return output


def build_visualization_dictionary(
    outputs: dict[str, pd.DataFrame],
    visibility: pd.DataFrame,
) -> pd.DataFrame:
    visibility_map = visibility.set_index("metric_id")[
        "visibility_tier"
    ].to_dict()
    rows: list[dict[str, object]] = []
    for dataset_name, frame in outputs.items():
        for column in frame.columns:
            rows.append(
                {
                    "visualization_version": VISUALIZATION_VERSION,
                    "dataset_name": dataset_name,
                    "field_name": column,
                    "pandas_dtype": str(frame[column].dtype),
                    "nullable": bool(frame[column].isna().any()),
                    "visibility_tier": visibility_map.get(
                        column, "SUPPORTING_OR_IDENTIFIER"
                    ),
                    "is_identifier": column.endswith("_id")
                    or column in {"case_id", "generation_id", "package_id"},
                    "is_rate": any(
                        token in column
                        for token in [
                            "rate",
                            "faithfulness",
                            "verifiability",
                            "yield",
                            "coverage",
                            "compliant",
                        ]
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_outputs(input_data: dict[str, Any]) -> dict[str, pd.DataFrame]:
    legacy_outputs = build_visualization_outputs(input_data["legacy"])
    outputs = {
        name: upgrade_legacy_output(frame)
        for name, frame in legacy_outputs.items()
        if name != "visualization_dictionary"
    }
    outputs.update(
        {
            "evidence_design_summary": build_evidence_design_summary(
                input_data
            ),
            "evidence_utilization_summary": (
                build_evidence_utilization_summary(input_data)
            ),
            "narrative_structure_summary": (
                build_narrative_structure_summary(input_data)
            ),
            "case_heterogeneity_summary": (
                build_case_heterogeneity_summary(input_data)
            ),
            "research_question_registry": build_rq_registry(
                input_data["rq_contract"]
            ),
            "metric_visibility_registry": build_metric_visibility_registry(
                input_data["metric_visibility"]
            ),
            "baseline_generation_metrics": upgrade_legacy_output(
                input_data["baseline_generation_metrics"]
            ),
            "baseline_option_performance": upgrade_legacy_output(
                input_data["baseline_option_performance"]
            ),
            "llm_vs_template_case_pairs": upgrade_legacy_output(
                input_data["llm_vs_template_case_pairs"]
            ),
            "llm_vs_template_summary": upgrade_legacy_output(
                input_data["llm_vs_template_summary"]
            ),
            "llm_vs_template_tests": upgrade_legacy_output(
                input_data["llm_vs_template_tests"]
            ),
            "descriptive_statistics": upgrade_legacy_output(
                input_data["descriptive_statistics"]
            ),
            "omnibus_tests": upgrade_legacy_output(
                input_data["omnibus_tests"]
            ),
            "paired_tests": upgrade_legacy_output(
                input_data["paired_tests"]
            ),
            "conditional_paired_tests": upgrade_legacy_output(
                input_data["conditional_paired_tests"]
            ),
            "complete_case_omnibus_tests": upgrade_legacy_output(
                input_data["complete_case_omnibus_tests"]
            ),
            "statistical_sensitivity_summary": upgrade_legacy_output(
                input_data["statistical_sensitivity_summary"]
            ),
            "unusable_generations": upgrade_legacy_output(
                input_data["unusable_generations"]
            ),
            "validator_generation_pairs": upgrade_legacy_output(
                input_data["validator_generation_pairs"]
            ),
            "validator_metric_summary": upgrade_legacy_output(
                input_data["validator_metric_summary"]
            ),
            "validator_sensitivity_tests": upgrade_legacy_output(
                input_data["validator_sensitivity_tests"]
            ),
            "certified_report_numbers": build_certified_report_numbers(
                input_data["report_numbers"]
            ),
            "release_metadata": build_release_metadata(input_data),
        }
    )
    outputs["visualization_dictionary"] = build_visualization_dictionary(
        outputs,
        outputs["metric_visibility_registry"],
    )
    return outputs


def write_outputs(outputs: dict[str, pd.DataFrame]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, path in OUTPUT_PATHS.items():
        outputs[name].to_csv(path, index=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))


def build_manifest(
    outputs: dict[str, pd.DataFrame],
    input_data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "visualization_manifest_v2",
        "visualization_version": VISUALIZATION_VERSION,
        "parent_analytical_gate": input_data["report_readiness"][
            "exit_gate"
        ],
        "baseline_gate": input_data["baseline_validation"]["exit_gate"],
        "research_questions": input_data["rq_contract"][
            "research_questions"
        ],
        "dashboard_contract_schema": input_data["dashboard_contract"].get(
            "schema_version"
        ),
        "template_baseline": {
            "enabled": True,
            "generator_count": 216,
            "is_fourth_llm": False,
            "eligible_for_decision_ranking": False,
            "human_naturalness_evaluated": False,
            "claim_extraction_channel_identical_to_llm": False,
        },
        "output_artifacts": [
            {
                "dataset_name": name,
                "path": relative(path),
                "row_count": int(len(outputs[name])),
                "column_count": int(len(outputs[name].columns)),
                "sha256": sha256_file(path),
            }
            for name, path in OUTPUT_PATHS.items()
        ],
        "validation_path": relative(VALIDATION_PATH),
        "manifest_path": relative(MANIFEST_PATH),
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
