"""Regression R4 cho leakage guards và preprocessing fit-on-train."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from research.ml.data_split.splitter import (
    build_split_stats,
    check_target_and_id_leakage,
)
from research.ml.preprocessing.transforms import (
    UNKNOWN_CATEGORY_TOKEN,
    apply_rare_category_mapping,
    fit_rare_category_mapping,
    transform_numeric,
    validate_model_ready_dataset,
    validate_raw_split_inputs,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class LeakageAndSplitTests(unittest.TestCase):
    def test_target_and_entity_ids_block_feature_matrix(self) -> None:
        frame = pd.DataFrame(
            {
                "SK_ID_CURR": [1, 2],
                "feature": [0.1, 0.2],
                "TARGET": [0, 1],
                "SK_ID_PREV": [10, 20],
            }
        )
        result = check_target_and_id_leakage(frame)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["forbidden_columns_found"], ["SK_ID_PREV", "TARGET"])

    def test_split_stats_require_disjoint_customer_ids(self) -> None:
        train_x = pd.DataFrame({"SK_ID_CURR": [1, 2, 3]})
        valid_x = pd.DataFrame({"SK_ID_CURR": [4]})
        test_x = pd.DataFrame({"SK_ID_CURR": [5]})
        train_y = pd.DataFrame({"SK_ID_CURR": [1, 2, 3], "TARGET": [0, 1, 0]})
        valid_y = pd.DataFrame({"SK_ID_CURR": [4], "TARGET": [0]})
        test_y = pd.DataFrame({"SK_ID_CURR": [5], "TARGET": [1]})

        result = build_split_stats(
            X_train=train_x,
            y_train=train_y,
            X_valid=valid_x,
            y_valid=valid_y,
            X_test=test_x,
            y_test=test_y,
            full_positive_rate=0.4,
            full_rows=5,
        )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["split_row_total"], 5)
        self.assertEqual(
            result["id_overlap_check"],
            {"train_valid_overlap": 0, "train_test_overlap": 0, "valid_test_overlap": 0},
        )


class SpyImputer:
    def __init__(self) -> None:
        self.fit_frame: pd.DataFrame | None = None
        self.fill_values: pd.Series | None = None

    def fit_transform(self, frame: pd.DataFrame) -> np.ndarray:
        self.fit_frame = frame.copy()
        self.fill_values = frame.median()
        return frame.fillna(self.fill_values).to_numpy()

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        assert self.fill_values is not None
        return frame.fillna(self.fill_values).to_numpy()


class SpyScaler:
    def __init__(self) -> None:
        self.fit_values: np.ndarray | None = None
        self.mean: np.ndarray | None = None

    def fit_transform(self, values: np.ndarray) -> np.ndarray:
        self.fit_values = values.copy()
        self.mean = values.mean(axis=0)
        return values - self.mean

    def transform(self, values: np.ndarray) -> np.ndarray:
        assert self.mean is not None
        return values - self.mean


class TrainOnlyPreprocessingTests(unittest.TestCase):
    def test_numeric_imputer_and_scaler_fit_only_train(self) -> None:
        train = pd.DataFrame({"feature": [1.0, np.nan]})
        valid = pd.DataFrame({"feature": [100.0]})
        test = pd.DataFrame({"feature": [-100.0]})
        imputer = SpyImputer()
        scaler = SpyScaler()

        with (
            patch(
                "research.ml.preprocessing.transforms.create_simple_imputer",
                return_value=imputer,
            ),
            patch(
                "research.ml.preprocessing.transforms.create_standard_scaler",
                return_value=scaler,
            ),
        ):
            train_ready, valid_ready, test_ready, _ = transform_numeric(
                X_train=train,
                X_valid=valid,
                X_test=test,
                numeric_features=["feature"],
                scaled=True,
            )

        self.assertEqual(imputer.fit_frame["feature"].tolist()[0], 1.0)
        self.assertTrue(pd.isna(imputer.fit_frame["feature"].tolist()[1]))
        self.assertEqual(scaler.fit_values.tolist(), [[1.0], [1.0]])
        self.assertEqual(list(train_ready.columns), ["feature"])
        self.assertEqual(list(valid_ready.columns), ["feature"])
        self.assertEqual(list(test_ready.columns), ["feature"])

    def test_unseen_valid_category_does_not_enter_train_mapping(self) -> None:
        train = pd.DataFrame({"category": ["A", "A", "B"]})
        valid = pd.DataFrame({"category": ["C"]})
        mapping = fit_rare_category_mapping(
            X_train=train,
            categorical_features=["category"],
            rare_threshold=0.5,
        )
        transformed_valid = apply_rare_category_mapping(
            X=valid,
            categorical_features=["category"],
            rare_mapping=mapping,
        )
        self.assertNotIn("C", mapping["category"]["kept_categories"])
        self.assertEqual(transformed_valid.iloc[0]["category"], UNKNOWN_CATEGORY_TOKEN)

    def test_input_validation_requires_same_feature_order(self) -> None:
        train_x = pd.DataFrame({"SK_ID_CURR": [1], "a": [1.0], "b": [2.0]})
        valid_x = pd.DataFrame({"SK_ID_CURR": [2], "b": [3.0], "a": [4.0]})
        test_x = pd.DataFrame({"SK_ID_CURR": [3], "a": [5.0], "b": [6.0]})
        train_y = pd.DataFrame({"SK_ID_CURR": [1], "TARGET": [0]})
        valid_y = pd.DataFrame({"SK_ID_CURR": [2], "TARGET": [1]})
        test_y = pd.DataFrame({"SK_ID_CURR": [3], "TARGET": [0]})
        metadata = {"a": {}, "b": {}}

        result = validate_raw_split_inputs(
            X_train=train_x,
            y_train=train_y,
            X_valid=valid_x,
            y_valid=valid_y,
            X_test=test_x,
            y_test=test_y,
            model_feature_columns=["a", "b"],
            id_columns=["SK_ID_CURR"],
            target_column="TARGET",
            feature_metadata=metadata,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("valid: X columns differ from train X columns", result["errors"])

    def test_model_ready_validation_rejects_nan_inf_and_column_drift(self) -> None:
        train = pd.DataFrame({"a": [1.0], "b": [2.0]})
        valid = pd.DataFrame({"b": [3.0], "a": [np.nan]})
        test = pd.DataFrame({"a": [np.inf], "b": [4.0]})
        result = validate_model_ready_dataset(train, valid, test, "fixture")
        self.assertEqual(result["status"], "blocked")
        self.assertGreater(result["valid_missing_count"], 0)
        self.assertGreater(result["test_inf_count"], 0)


class OfficialManifestGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configured_root = os.environ.get("RESEARCH_GOLDEN_ROOT")
        cls.golden_root = Path(configured_root) if configured_root else REPOSITORY_ROOT
        split_manifest = cls.golden_root / "data/manifests/split_manifest.json"
        if not split_manifest.exists():
            raise unittest.SkipTest("Worktree không chứa official manifests; cần RESEARCH_GOLDEN_ROOT.")

    def test_split_counts_seed_and_overlap_match_baseline(self) -> None:
        manifest_path = self.golden_root / "data/manifests/split_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        stats = manifest["split_stats"]
        self.assertEqual(manifest["split_config"]["random_state"], 42)
        self.assertEqual(stats["splits"]["train"]["rows"], 215_257)
        self.assertEqual(stats["splits"]["valid"]["rows"], 46_127)
        self.assertEqual(stats["splits"]["test"]["rows"], 46_127)
        self.assertEqual(sum(stats["id_overlap_check"].values()), 0)

    def test_preprocessed_columns_and_validation_match_baseline(self) -> None:
        manifest_path = self.golden_root / "data/manifests/preprocessing_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["strategy"]["fit_on"], "train_only")
        self.assertEqual(manifest["validation"]["tree_validation"]["preprocessed_feature_count"], 213)
        self.assertEqual(manifest["validation"]["linear_validation"]["preprocessed_feature_count"], 213)
        self.assertEqual(manifest["validation"]["tree_validation"]["train_missing_count"], 0)
        self.assertEqual(manifest["validation"]["tree_validation"]["train_inf_count"], 0)

        tree_columns = json.loads(
            (self.golden_root / "ml/registry/preprocessed_feature_columns_tree.json").read_text()
        )
        linear_columns = json.loads(
            (self.golden_root / "ml/registry/preprocessed_feature_columns_linear.json").read_text()
        )
        self.assertEqual(len(tree_columns), 213)
        self.assertEqual(tree_columns, linear_columns)


if __name__ == "__main__":
    unittest.main()
