from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.python.common.hashing import sha256_file
from research.python.common_ml.context import CommonMLRunContext
from research.python.common_ml.modeling import run_common_modeling
from research.python.common_ml.preprocessing import run_common_preprocessing
from research.python.common_ml.split import CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN, run_common_split
from research.python.datasets.profile import sha256_json




@pytest.fixture(autouse=True)
def _parquet_engine_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use pickle-backed parquet shims only in this dependency-light test sandbox."""
    def write_pickle(self: pd.DataFrame, path, index: bool = False, **kwargs) -> None:
        frame = self.reset_index(drop=True) if not index else self
        frame.to_pickle(path)

    def read_pickle(path, **kwargs) -> pd.DataFrame:
        return pd.read_pickle(path)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", write_pickle)
    monkeypatch.setattr(pd, "read_parquet", read_pickle)


FEATURES = [
    "annual_resources",
    "revolving_load",
    "late_events_90d",
    "employment_band",
    "has_collateral_flag",
    "account_age_months",
]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _make_fixture(tmp_path: Path, dataset_id: str = "independent_credit_fixture") -> CommonMLRunContext:
    artifact_root = tmp_path / "source_artifacts"
    (artifact_root / "data/processed").mkdir(parents=True)
    (artifact_root / "ml/registry").mkdir(parents=True)

    rng = np.random.default_rng(123)
    n = 240
    ids = [f"B-{i:04d}" for i in range(n)]
    annual = rng.normal(60_000, 15_000, n).clip(10_000)
    revolving = rng.uniform(0, 1, n)
    late = rng.poisson(1.1, n)
    employment = rng.choice(["stable", "contract", "new"], n, p=[0.55, 0.25, 0.20])
    collateral = rng.integers(0, 2, n)
    age_months = rng.integers(1, 180, n)
    logit = 2.4 * revolving + 0.55 * late - annual / 80_000 - 0.35 * collateral
    probability = 1 / (1 + np.exp(-(logit - np.quantile(logit, 0.65))))
    target_binary = rng.binomial(1, probability)
    # Guarantee both classes and enough positives for stratification.
    assert target_binary.min() == 0 and target_binary.max() == 1

    X = pd.DataFrame(
        {
            "borrower_key": ids,
            "annual_resources": annual,
            "revolving_load": revolving,
            "late_events_90d": late,
            "employment_band": employment,
            "has_collateral_flag": collateral,
            "account_age_months": age_months,
        }
    )
    y = pd.DataFrame(
        {
            "borrower_key": ids,
            "bad_12m": np.where(target_binary == 1, "Y", "N"),
        }
    )
    feature_path = artifact_root / "data/processed/feature_matrix_full.parquet"
    target_path = artifact_root / "data/processed/target_full.parquet"
    X.to_parquet(feature_path, index=False)
    y.to_parquet(target_path, index=False)

    registry = pd.DataFrame(
        [
            {"feature_name": "annual_resources", "data_kind": "numeric", "value_type": "amount", "concept": "financial_capacity", "allowed_for_model": True},
            {"feature_name": "revolving_load", "data_kind": "numeric", "value_type": "ratio", "concept": "credit_utilization", "allowed_for_model": True},
            {"feature_name": "late_events_90d", "data_kind": "numeric", "value_type": "count", "concept": "delinquency_history", "allowed_for_model": True},
            {"feature_name": "employment_band", "data_kind": "categorical", "value_type": "categorical", "concept": "employment_stability", "allowed_for_model": True},
            {"feature_name": "has_collateral_flag", "data_kind": "binary", "value_type": "binary_indicator", "concept": "loan_security", "allowed_for_model": True},
            {"feature_name": "account_age_months", "data_kind": "numeric", "value_type": "duration", "concept": "credit_history", "allowed_for_model": True},
        ]
    )
    registry_csv = artifact_root / "ml/registry/feature_registry.csv"
    registry.to_csv(registry_csv, index=False)
    registry_yaml = artifact_root / "ml/registry/feature_registry.yaml"
    registry_yaml.write_text("schema_version: fixture\nfeatures: {}\n", encoding="utf-8")
    concept_yaml = artifact_root / "ml/registry/concept_registry.yaml"
    concept_yaml.write_text("schema_version: fixture\nconcepts: {}\n", encoding="utf-8")

    profile = {
        "schema_version": "dataset_profile_v1",
        "dataset_id": dataset_id,
        "dataset_version": "v1",
        "domain": "credit_risk",
        "task_type": "binary_classification",
        "entity": {"entity_type": "borrower", "source_id_column": "borrower_key"},
        "target": {
            "source_column": "bad_12m",
            "canonical_name": "target",
            "positive_value": "Y",
            "negative_value": "N",
            "semantic_name": "default_within_12_months",
            "prediction_horizon": "12_months",
        },
        "adapter": {"adapter_id": "fixture_adapter", "adapter_version": "v1"},
        "capabilities": {
            "supports_stratified_split": True,
            "supports_feature_level_xai": True,
            "supports_semantic_registry": True,
            "supports_case_strata": True,
            "supports_adaptive_evidence": True,
            "has_stable_entity_id": True,
            "feature_count": len(FEATURES),
        },
    }
    profile_path = tmp_path / "dataset_profile.json"
    _write_json(profile_path, profile)

    refs = {
        "feature_matrix": feature_path,
        "target": target_path,
        "feature_registry_csv": registry_csv,
        "feature_registry_yaml": registry_yaml,
        "concept_registry_yaml": concept_yaml,
    }
    bundle = {
        "schema_version": "canonical_dataset_bundle_v1",
        "dataset_id": dataset_id,
        "dataset_version": "v1",
        "dataset_fingerprint": "a" * 64,
        "dataset_profile_sha256": sha256_json(profile),
        "artifacts": {
            name: {
                "path": str(path.relative_to(artifact_root)),
                "sha256": sha256_file(path),
                "required": True,
            }
            for name, path in refs.items()
        },
        "provenance": {
            "adapter_id": "fixture_adapter",
            "adapter_version": "v1",
            "artifact_source_root_locator": str(artifact_root),
        },
    }
    bundle_path = tmp_path / "canonical_bundle.json"
    _write_json(bundle_path, bundle)

    project_root = tmp_path / "project"
    project_root.mkdir()
    return CommonMLRunContext.load(
        dataset_profile_path=profile_path,
        canonical_bundle_path=bundle_path,
        experiment_id="fixture_replication_v1",
        run_id="run-001",
        project_root=project_root,
    )


def test_common_split_normalizes_dataset_specific_identity_and_target(tmp_path: Path) -> None:
    ctx = _make_fixture(tmp_path)
    result = run_common_split(ctx)
    assert result.model_feature_count == len(FEATURES)
    train_x = pd.read_parquet(result.split_dir / "X_train.parquet")
    train_y = pd.read_parquet(result.split_dir / "y_train.parquet")
    assert list(train_x.columns[:2]) == [CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN]
    assert "borrower_key" not in train_x.columns
    assert "bad_12m" not in train_x.columns
    assert list(train_y.columns) == [CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN, "target"]
    assert set(train_y["target"].unique()) == {0, 1}
    assert all(value.startswith("case_independent_credit_fixture_borrower_") for value in train_y[CASE_ID_COLUMN])


def test_common_split_preprocessing_modeling_runs_with_non_home_credit_schema(tmp_path: Path) -> None:
    ctx = _make_fixture(tmp_path)
    split = run_common_split(ctx)
    prep = run_common_preprocessing(ctx)
    model = run_common_modeling(ctx)

    assert split.train_rows + split.valid_rows + split.test_rows == 240
    assert prep.tree_feature_count >= len(FEATURES)
    assert prep.linear_feature_count == prep.tree_feature_count
    assert model.best_model_name in {
        "logistic_regression",
        "random_forest",
        "hist_gradient_boosting",
    }
    assert model.best_model_path.is_file()
    registry = json.loads((ctx.paths.registry_dir / "model_registry.json").read_text())
    assert registry["dataset_id"] == "independent_credit_fixture"
    assert registry["selection_policy"]["primary"] == "average_precision"
    assert len(registry["models"]) == 3


def test_common_ml_source_has_no_home_credit_column_dependency() -> None:
    root = Path(__file__).resolve().parents[4]
    common_ml = root / "research/python/common_ml"
    source = "\n".join(path.read_text(encoding="utf-8") for path in common_ml.glob("*.py"))
    assert "SK_ID_CURR" not in source
    assert "SK_ID_BUREAU" not in source
    assert "SK_ID_PREV" not in source
