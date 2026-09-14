from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def repo_relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def record_file(root: Path, path: Path, *, rows: int | None = None) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    record: dict[str, Any] = {
        "path": repo_relative(root, path),
        "sha256": sha256_file(path),
        "byte_count": path.stat().st_size,
    }
    if rows is not None:
        record["row_count"] = int(rows)
    return record


def resolve_record(root: Path, record: dict[str, Any], label: str) -> Path:
    path = Path(str(record["path"]))
    path = path if path.is_absolute() else root / path
    if not path.is_file():
        raise FileNotFoundError(f"{label}: {path}")
    if sha256_file(path) != str(record["sha256"]):
        raise ValueError(f"{label} SHA mismatch: {path}")
    if "byte_count" in record and path.stat().st_size != int(record["byte_count"]):
        raise ValueError(f"{label} byte-count mismatch: {path}")
    return path


def derive_complete_case_ids(metrics: pd.DataFrame) -> list[str]:
    required = {"case_id", "model_id", "evidence_level", "usable"}
    missing = sorted(required - set(metrics.columns))
    if missing:
        raise ValueError(f"Generation metrics missing complete-case fields: {missing}")
    keys = metrics[["case_id", "model_id", "evidence_level"]].astype(str)
    if keys.duplicated().any():
        raise ValueError("Duplicate case × model × evidence rows in generation metrics.")
    per_case_rows = metrics.groupby(metrics["case_id"].astype(str), sort=False).size()
    expected_conditions = int(metrics["model_id"].nunique() * metrics["evidence_level"].nunique())
    if not per_case_rows.eq(expected_conditions).all():
        raise ValueError("Every canonical case must expose all model × evidence conditions.")
    usable_all = metrics.assign(case_key=metrics["case_id"].astype(str)).groupby("case_key", sort=False)["usable"].all()
    return sorted(usable_all.loc[usable_all].index.astype(str).tolist())


def option_ids(metrics: pd.DataFrame) -> list[str]:
    values = metrics["model_id"].astype(str) + "::" + metrics["evidence_level"].astype(str)
    return sorted(values.unique().tolist())


def claim_types(claims: pd.DataFrame) -> list[str]:
    if "claim_type" not in claims.columns:
        raise ValueError("Claim diagnostics missing claim_type.")
    return sorted(claims["claim_type"].dropna().astype(str).unique().tolist())
