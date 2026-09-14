"""Build generation-level Candidate-versus-V4 sensitivity outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.python.statistical_analysis.inference import (
    holm_adjust,
    rank_biserial_correlation,
)

from .config import METRICS, SENSITIVITY_VERSION


COUNT_COLUMNS = [
    "total_claims",
    "supported_count",
    "unsupported_count",
    "contradicted_count",
    "not_verifiable_count",
    "not_applicable_count",
]
IDENTITY_COLUMNS = [
    "generation_id",
    "case_id",
    "model_id",
    "evidence_level",
    "repeat_id",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a non-empty JSONL artifact."""

    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected object at {path}:{line_number}")
            records.append(value)
    if not records:
        raise ValueError(f"Validator summary is empty: {path}")
    return records


def add_validator_metrics(
    records: list[dict[str, Any]],
    validator_id: str,
) -> pd.DataFrame:
    """Calculate the same generation metrics for one validator summary."""

    frame = pd.DataFrame(records).copy()
    frame["case_id"] = frame["case_id"].astype(str)
    frame[COUNT_COLUMNS] = frame[COUNT_COLUMNS].fillna(0).astype(int)
    frame["applicable_count"] = (
        frame["supported_count"]
        + frame["unsupported_count"]
        + frame["contradicted_count"]
        + frame["not_verifiable_count"]
    )
    frame["resolved_count"] = (
        frame["supported_count"]
        + frame["unsupported_count"]
        + frame["contradicted_count"]
    )

    usable = frame["usable"].astype(bool)
    applicable = frame["applicable_count"]
    resolved = frame["resolved_count"]
    supported = frame["supported_count"]

    frame["resolved_faithfulness"] = np.where(
        usable & resolved.gt(0),
        supported / resolved,
        np.nan,
    )
    frame["verifiability"] = np.where(
        usable & applicable.gt(0),
        resolved / applicable,
        np.nan,
    )
    frame["conservative_faithfulness"] = np.where(
        usable & applicable.gt(0),
        supported / applicable,
        np.nan,
    )
    frame["end_to_end_faithfulness_yield"] = (
        frame["conservative_faithfulness"].fillna(0.0)
    )
    frame["validator_id"] = validator_id

    return frame[
        IDENTITY_COLUMNS
        + ["usable"]
        + COUNT_COLUMNS
        + ["resolved_count", "applicable_count"]
        + METRICS
        + ["validator_id"]
    ]


def build_validator_pairs(
    candidate_records: list[dict[str, Any]],
    v4_records: list[dict[str, Any]],
) -> pd.DataFrame:
    """Pair both validators on the same 648 generation identities."""

    candidate = add_validator_metrics(candidate_records, "candidate")
    v4 = add_validator_metrics(v4_records, "v4")
    pairs = candidate.merge(
        v4,
        on="generation_id",
        how="outer",
        validate="one_to_one",
        suffixes=("_candidate", "_v4"),
        indicator=True,
    )

    mismatch = pairs["_merge"].ne("both")
    for column in IDENTITY_COLUMNS[1:]:
        mismatch |= pairs[f"{column}_candidate"].astype(str).ne(
            pairs[f"{column}_v4"].astype(str)
        )
    if mismatch.any():
        raise ValueError(
            "Candidate and V4 generation identities do not reconcile."
        )

    output = pd.DataFrame(
        {
            "sensitivity_version": SENSITIVITY_VERSION,
            "generation_id": pairs["generation_id"],
            "case_id": pairs["case_id_candidate"].astype(str),
            "model_id": pairs["model_id_candidate"],
            "evidence_level": pairs["evidence_level_candidate"],
            "repeat_id": pairs["repeat_id_candidate"],
            "usable": pairs["usable_candidate"].astype(bool),
        }
    )
    for column in COUNT_COLUMNS + [
        "resolved_count",
        "applicable_count",
        *METRICS,
    ]:
        output[f"candidate_{column}"] = pairs[f"{column}_candidate"]
        output[f"v4_{column}"] = pairs[f"{column}_v4"]
        output[f"delta_{column}"] = (
            output[f"v4_{column}"]
            - output[f"candidate_{column}"]
        )

    return output.sort_values(
        ["model_id", "evidence_level", "case_id", "generation_id"],
        kind="stable",
    ).reset_index(drop=True)


def build_metric_summary(pairs: pd.DataFrame) -> pd.DataFrame:
    """Summarize measurement sensitivity at audited reporting grains."""

    group_specs = [
        ("overall", []),
        ("model", ["model_id"]),
        ("evidence", ["evidence_level"]),
        ("model_evidence", ["model_id", "evidence_level"]),
    ]
    rows: list[dict[str, Any]] = []

    for group_type, columns in group_specs:
        grouped = [((), pairs)] if not columns else pairs.groupby(columns, sort=False)
        for keys, group in grouped:
            if not isinstance(keys, tuple):
                keys = (keys,)
            identity = dict(zip(columns, keys, strict=False))
            for metric_id in METRICS:
                delta = group[f"delta_{metric_id}"].dropna()
                rows.append(
                    {
                        "sensitivity_version": SENSITIVITY_VERSION,
                        "group_type": group_type,
                        "model_id": identity.get("model_id"),
                        "evidence_level": identity.get("evidence_level"),
                        "metric_id": metric_id,
                        "generation_count": len(group),
                        "candidate_mean": group[f"candidate_{metric_id}"].mean(),
                        "v4_mean": group[f"v4_{metric_id}"].mean(),
                        "mean_delta_v4_minus_candidate": delta.mean(),
                        "median_delta_v4_minus_candidate": delta.median(),
                    }
                )

    return pd.DataFrame(rows)


def _wilcoxon_from_case_means(
    case_means: pd.DataFrame,
    metric_id: str,
) -> dict[str, float | int]:
    candidate = case_means[f"candidate_{metric_id}"].to_numpy(dtype=float)
    v4 = case_means[f"v4_{metric_id}"].to_numpy(dtype=float)
    differences = v4 - candidate

    if np.allclose(differences, 0.0, rtol=0.0, atol=1e-15):
        statistic = 0.0
        p_value = 1.0
    else:
        from scipy.stats import wilcoxon

        result = wilcoxon(
            differences,
            zero_method="wilcox",
            correction=False,
            alternative="two-sided",
            method="auto",
        )
        statistic = float(result.statistic)
        p_value = float(result.pvalue)

    return {
        "paired_case_count": int(len(case_means)),
        "candidate_case_mean": float(candidate.mean()),
        "v4_case_mean": float(v4.mean()),
        "mean_delta_v4_minus_candidate": float(differences.mean()),
        "median_delta_v4_minus_candidate": float(np.median(differences)),
        "wilcoxon_statistic": statistic,
        "raw_p_value": p_value,
        "rank_biserial_correlation": float(
            rank_biserial_correlation(differences)
        ),
    }


def build_sensitivity_tests(pairs: pd.DataFrame) -> pd.DataFrame:
    """Test validator sensitivity using case-level aggregated observations."""

    scopes: list[tuple[str, str, pd.DataFrame]] = [
        ("OVERALL", "ALL", pairs),
    ]
    for evidence_level, group in pairs.groupby("evidence_level", sort=False):
        scopes.append(("EVIDENCE", str(evidence_level), group))
    for model_id, group in pairs.groupby("model_id", sort=False):
        scopes.append(("MODEL", str(model_id), group))

    rows: list[dict[str, Any]] = []
    for scope_family, scope_id, group in scopes:
        for metric_id in METRICS:
            case_means = group.groupby("case_id", as_index=False)[
                [f"candidate_{metric_id}", f"v4_{metric_id}"]
            ].mean()
            rows.append(
                {
                    "sensitivity_version": SENSITIVITY_VERSION,
                    "analysis_role": "VALIDATOR_SENSITIVITY",
                    "scope_family": scope_family,
                    "scope_id": scope_id,
                    "metric_id": metric_id,
                    **_wilcoxon_from_case_means(case_means, metric_id),
                }
            )

    output = pd.DataFrame(rows)
    output["adjusted_p_value"] = output.groupby(
        ["scope_family", "metric_id"],
        sort=False,
    )["raw_p_value"].transform(holm_adjust)
    output["adjustment_method"] = "holm"
    output["significant_adjusted"] = output["adjusted_p_value"] < 0.05
    output["interpretation"] = np.where(
        output["significant_adjusted"],
        "Validator choice materially changes this metric at the planned case-level scope.",
        "No statistically supported validator sensitivity at this planned case-level scope; this is not equivalence.",
    )
    return output


def build_outputs(
    candidate_records: list[dict[str, Any]],
    v4_records: list[dict[str, Any]],
) -> dict[str, pd.DataFrame]:
    pairs = build_validator_pairs(candidate_records, v4_records)
    return {
        "pairs": pairs,
        "summary": build_metric_summary(pairs),
        "tests": build_sensitivity_tests(pairs),
    }
