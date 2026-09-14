from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..datasets.identity import canonical_case_id
from .context import CommonMLRunContext


CASE_ID_COLUMN = "case_id"
SOURCE_ENTITY_ID_COLUMN = "source_entity_id"
RANDOM_STATE = 42
TRAIN_RATIO = 0.70
VALID_RATIO = 0.15
TEST_RATIO = 0.15


@dataclass(frozen=True)
class CommonSplitResult:
    manifest_path: Path
    split_dir: Path
    model_feature_count: int
    train_rows: int
    valid_rows: int
    test_rows: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _bool_false(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"false", "0", "no"})


def _load_and_validate_inputs(ctx: CommonMLRunContext) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    feature_path = ctx.resolve_bundle_artifact("feature_matrix")
    target_path = ctx.resolve_bundle_artifact("target")
    registry_path = ctx.resolve_bundle_artifact("feature_registry_csv")

    X = pd.read_parquet(feature_path)
    y = pd.read_parquet(target_path)
    registry = pd.read_csv(registry_path)

    source_id = ctx.source_id_column
    source_target = ctx.source_target_column

    errors: list[str] = []
    if source_id not in X.columns:
        errors.append(f"feature_matrix missing source ID column {source_id!r}")
    if source_id not in y.columns:
        errors.append(f"target artifact missing source ID column {source_id!r}")
    if source_target not in y.columns:
        errors.append(f"target artifact missing source target column {source_target!r}")
    if source_target in X.columns:
        errors.append(f"target leakage: source target column {source_target!r} found in feature_matrix")
    if "feature_name" not in registry.columns:
        errors.append("feature_registry_csv missing feature_name column")
    if errors:
        raise ValueError("Canonical split input validation failed: " + "; ".join(errors))

    if X[source_id].isna().any() or y[source_id].isna().any():
        raise ValueError("Source entity ID contains missing values")
    if X[source_id].duplicated().any():
        raise ValueError("feature_matrix source entity IDs are not unique")
    if y[source_id].duplicated().any():
        raise ValueError("target source entity IDs are not unique")
    if len(X) != len(y):
        raise ValueError(f"feature/target row count mismatch: {len(X)} != {len(y)}")
    if set(X[source_id].astype(str)) != set(y[source_id].astype(str)):
        raise ValueError("feature_matrix and target source ID sets do not match")

    allowed_values = {
        str(ctx.profile.target.negative_value),
        str(ctx.profile.target.positive_value),
    }
    actual_values = set(y[source_target].dropna().map(str).unique().tolist())
    if actual_values != allowed_values:
        raise ValueError(
            "Source target values do not exactly match TargetContract: "
            f"actual={sorted(actual_values)}, expected={sorted(allowed_values)}"
        )
    if y[source_target].isna().any():
        raise ValueError("Source target contains missing values")

    return X, y, registry


def _canonicalize(
    *,
    ctx: CommonMLRunContext,
    X: pd.DataFrame,
    y: pd.DataFrame,
    registry: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], dict[str, Any]]:
    source_id = ctx.source_id_column
    source_target = ctx.source_target_column
    canonical_target = ctx.canonical_target_column

    y_lookup = y[[source_id, source_target]].copy()
    full = X.merge(y_lookup, on=source_id, how="inner", validate="one_to_one")
    if len(full) != len(X):
        raise ValueError("Canonical X/y merge changed row count")

    raw_source_ids = full[source_id].astype(str)
    case_ids = raw_source_ids.map(
        lambda value: canonical_case_id(
            ctx.profile.dataset_id,
            ctx.profile.entity.entity_type,
            value,
        )
    )
    if case_ids.duplicated().any():
        raise ValueError("Canonical case IDs collided within the dataset")

    negative = str(ctx.profile.target.negative_value)
    positive = str(ctx.profile.target.positive_value)
    mapped_target = full[source_target].map(str).map({negative: 0, positive: 1})
    if mapped_target.isna().any():
        raise ValueError("TargetContract mapping produced missing canonical targets")

    candidate_features = [
        column
        for column in X.columns
        if column != source_id
    ]
    registry_features = set(registry["feature_name"].astype(str).tolist())
    missing_registry = sorted(set(candidate_features) - registry_features)
    if missing_registry:
        raise ValueError(
            "Canonical feature matrix contains features without registry entries: "
            f"{missing_registry[:50]}"
        )

    blocked_features: list[str] = []
    if "allowed_for_model" in registry.columns:
        blocked_features = sorted(
            registry.loc[_bool_false(registry["allowed_for_model"]), "feature_name"]
            .astype(str)
            .tolist()
        )
    model_features = [column for column in candidate_features if column not in blocked_features]
    if not model_features:
        raise ValueError("No model features remain after registry filtering")

    canonical_X = full[model_features].copy()
    canonical_X.insert(0, SOURCE_ENTITY_ID_COLUMN, raw_source_ids.to_numpy())
    canonical_X.insert(0, CASE_ID_COLUMN, case_ids.to_numpy())

    canonical_y = pd.DataFrame(
        {
            CASE_ID_COLUMN: case_ids.to_numpy(),
            SOURCE_ENTITY_ID_COLUMN: raw_source_ids.to_numpy(),
            canonical_target: mapped_target.astype(int).to_numpy(),
        }
    )

    metadata = {
        "dataset_id": ctx.profile.dataset_id,
        "dataset_version": ctx.profile.dataset_version,
        "dataset_fingerprint": ctx.bundle.dataset_fingerprint,
        "entity_type": ctx.profile.entity.entity_type,
        "source_id_column": source_id,
        "source_target_column": source_target,
        "canonical_case_id_column": CASE_ID_COLUMN,
        "canonical_source_entity_id_column": SOURCE_ENTITY_ID_COLUMN,
        "canonical_target_column": canonical_target,
        "positive_source_value": ctx.profile.target.positive_value,
        "negative_source_value": ctx.profile.target.negative_value,
        "model_feature_columns": model_features,
        "model_feature_count": len(model_features),
        "excluded_registry_features": blocked_features,
    }
    return canonical_X, canonical_y, model_features, metadata


def _split(
    *,
    X: pd.DataFrame,
    y: pd.DataFrame,
    target_column: str,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    from sklearn.model_selection import train_test_split

    full = X.merge(y[[CASE_ID_COLUMN, target_column]], on=CASE_ID_COLUMN, validate="one_to_one")
    if full[target_column].nunique() != 2:
        raise ValueError("Canonical target must contain two classes for stratified split")

    train_df, temp_df = train_test_split(
        full,
        test_size=VALID_RATIO + TEST_RATIO,
        random_state=RANDOM_STATE,
        stratify=full[target_column],
    )
    valid_df, test_df = train_test_split(
        temp_df,
        test_size=TEST_RATIO / (VALID_RATIO + TEST_RATIO),
        random_state=RANDOM_STATE,
        stratify=temp_df[target_column],
    )

    parts: dict[str, pd.DataFrame] = {}
    stats: dict[str, Any] = {}
    full_rate = float(full[target_column].mean())
    for name, frame in (("train", train_df), ("valid", valid_df), ("test", test_df)):
        x_part = frame.drop(columns=[target_column]).reset_index(drop=True)
        y_part = frame[[CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN, target_column]].reset_index(drop=True)
        parts[f"X_{name}"] = x_part
        parts[f"y_{name}"] = y_part
        stats[name] = {
            "rows": int(len(frame)),
            "positive_count": int((frame[target_column] == 1).sum()),
            "negative_count": int((frame[target_column] == 0).sum()),
            "positive_rate": float(frame[target_column].mean()),
            "target_rate_gap_from_full": abs(float(frame[target_column].mean()) - full_rate),
        }

    id_sets = {
        name: set(parts[f"X_{name}"][CASE_ID_COLUMN].tolist())
        for name in ("train", "valid", "test")
    }
    overlaps = {
        "train_valid_overlap": len(id_sets["train"] & id_sets["valid"]),
        "train_test_overlap": len(id_sets["train"] & id_sets["test"]),
        "valid_test_overlap": len(id_sets["valid"] & id_sets["test"]),
    }
    if any(overlaps.values()):
        raise ValueError(f"Canonical split case ID overlap detected: {overlaps}")
    if sum(item["rows"] for item in stats.values()) != len(full):
        raise ValueError("Canonical split row total does not match full dataset")

    split_stats = {
        "strategy": "stratified_binary_target",
        "random_state": RANDOM_STATE,
        "ratios": {"train": TRAIN_RATIO, "valid": VALID_RATIO, "test": TEST_RATIO},
        "full_rows": int(len(full)),
        "full_positive_rate": full_rate,
        "splits": stats,
        "case_id_overlap": overlaps,
    }
    return parts, split_stats


def _copy_semantic_registries(ctx: CommonMLRunContext) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for artifact_name, output_name in (
        ("feature_registry_csv", "feature_registry.csv"),
        ("feature_registry_yaml", "feature_registry.yaml"),
        ("concept_registry_yaml", "concept_registry.yaml"),
    ):
        source = ctx.resolve_bundle_artifact(artifact_name)
        destination = ctx.paths.registry_dir / output_name
        shutil.copy2(source, destination)
        outputs[artifact_name] = str(destination)
    return outputs


def run_common_split(ctx: CommonMLRunContext) -> CommonSplitResult:
    if not ctx.profile.capabilities.supports_stratified_split:
        raise ValueError("DatasetProfile declares supports_stratified_split=false")
    ctx.create_workspace()

    X, y, registry = _load_and_validate_inputs(ctx)
    canonical_X, canonical_y, model_features, feature_metadata = _canonicalize(
        ctx=ctx,
        X=X,
        y=y,
        registry=registry,
    )
    parts, split_stats = _split(
        X=canonical_X,
        y=canonical_y,
        target_column=ctx.canonical_target_column,
    )

    split_dir = ctx.paths.processed_dir / "splits"
    output_files: dict[str, str] = {}
    for key, frame in parts.items():
        path = split_dir / f"{key}.parquet"
        frame.to_parquet(path, index=False)
        output_files[key] = str(path)

    _json_write(ctx.paths.registry_dir / "model_feature_columns.json", model_features)
    _json_write(
        ctx.paths.registry_dir / "id_columns.json",
        [CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN],
    )
    _json_write(ctx.paths.registry_dir / "target_column.json", ctx.canonical_target_column)
    _json_write(ctx.paths.registry_dir / "model_feature_metadata.json", feature_metadata)
    registry_outputs = _copy_semantic_registries(ctx)

    manifest = {
        "schema_version": "common_ml_split_manifest_v1",
        "created_at_utc": _utc_now(),
        **ctx.common_provenance(),
        "canonical_columns": {
            "case_id": CASE_ID_COLUMN,
            "source_entity_id": SOURCE_ENTITY_ID_COLUMN,
            "target": ctx.canonical_target_column,
        },
        "source_contract": {
            "source_id_column": ctx.source_id_column,
            "source_target_column": ctx.source_target_column,
            "target_semantic_name": ctx.profile.target.semantic_name,
            "prediction_horizon": ctx.profile.target.prediction_horizon,
        },
        "model_feature_count": len(model_features),
        "model_feature_columns": model_features,
        "split_stats": split_stats,
        "output_files": output_files,
        "registry_outputs": registry_outputs,
        "status": "passed",
    }
    manifest_path = ctx.paths.manifest_dir / "common_ml_split_manifest.json"
    _json_write(manifest_path, manifest)

    return CommonSplitResult(
        manifest_path=manifest_path,
        split_dir=split_dir,
        model_feature_count=len(model_features),
        train_rows=split_stats["splits"]["train"]["rows"],
        valid_rows=split_stats["splits"]["valid"]["rows"],
        test_rows=split_stats["splits"]["test"]["rows"],
    )
