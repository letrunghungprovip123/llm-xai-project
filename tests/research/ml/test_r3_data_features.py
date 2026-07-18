"""Regression nhỏ cho data audit, feature groups và registry ở R3."""

from __future__ import annotations

import ast
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from research.ml.common.dataframes import (
    count_infinite_values,
    replace_infinite_with_nan,
)
from research.ml.common.hashing import sha256_file
from research.ml.feature_engineering.feature_groups import (
    safe_divide,
    validate_feature_group,
)
from research.ml.feature_matrix.matrix_registry import validate_final_matrix


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class SharedHelperTests(unittest.TestCase):
    def test_sha256_file_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            source = Path(temporary_dir) / "fixture.txt"
            source.write_bytes(b"llm-xai-next\n")
            self.assertEqual(
                sha256_file(source),
                "3dac18d4b248296fc82b8ba3590560b1721bb0dbc89d52177bd7d36377cf62a8",
            )

    def test_infinite_values_are_counted_and_normalized(self) -> None:
        frame = pd.DataFrame({"value": [1.0, np.inf, -np.inf], "label": ["a", "b", "c"]})
        self.assertEqual(count_infinite_values(frame), 2)
        normalized = replace_infinite_with_nan(frame)
        self.assertEqual(int(normalized["value"].isna().sum()), 2)


class FeatureInvariantTests(unittest.TestCase):
    def test_safe_divide_rejects_zero_denominator(self) -> None:
        result = safe_divide(pd.Series([4.0, 2.0]), pd.Series([2.0, 0.0]))
        self.assertEqual(result.iloc[0], 2.0)
        self.assertTrue(pd.isna(result.iloc[1]))

    def test_feature_group_requires_one_row_per_customer(self) -> None:
        frame = pd.DataFrame({"SK_ID_CURR": [1, 1], "feature": [0.1, 0.2]})
        stats = validate_feature_group(frame, "fixture")
        self.assertEqual(stats["status"], "blocked")
        self.assertEqual(stats["duplicate_sk_id_curr"], 1)

    def test_target_and_entity_ids_are_forbidden(self) -> None:
        frame = pd.DataFrame(
            {
                "SK_ID_CURR": [1, 2],
                "TARGET": [0, 1],
                "SK_ID_PREV": [10, 20],
            }
        )
        group_stats = validate_feature_group(frame, "fixture")
        matrix_stats = validate_final_matrix(frame, expected_rows=2)
        self.assertEqual(group_stats["forbidden_columns_found"], ["SK_ID_PREV", "TARGET"])
        self.assertEqual(matrix_stats["forbidden_columns_found"], ["SK_ID_PREV", "TARGET"])

    def test_valid_matrix_keeps_feature_count(self) -> None:
        frame = pd.DataFrame(
            {
                "SK_ID_CURR": [1, 2],
                "numeric_feature": [0.1, 0.2],
                "category_feature": ["a", "b"],
            }
        )
        stats = validate_final_matrix(frame, expected_rows=2)
        self.assertEqual(stats["status"], "passed")
        self.assertEqual(stats["feature_count"], 2)
        self.assertEqual(stats["numeric_feature_count"], 1)
        self.assertEqual(stats["categorical_feature_count"], 1)


class ImportBoundaryTests(unittest.TestCase):
    def test_active_r3_modules_do_not_create_directories_at_import(self) -> None:
        module_paths = [
            REPOSITORY_ROOT / "research/ml/data_audit/pipeline.py",
            REPOSITORY_ROOT / "research/ml/target_audit/pipeline.py",
            REPOSITORY_ROOT / "research/ml/feature_engineering/feature_groups.py",
            REPOSITORY_ROOT / "research/ml/feature_matrix/matrix_registry.py",
        ]
        for module_path in module_paths:
            syntax_tree = ast.parse(module_path.read_text(encoding="utf-8"))
            top_level_mkdir = [
                statement
                for statement in syntax_tree.body
                if isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Attribute)
                and statement.value.func.attr == "mkdir"
            ]
            self.assertEqual(top_level_mkdir, [], module_path)


class OfficialManifestGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configured_root = os.environ.get("RESEARCH_GOLDEN_ROOT")
        cls.golden_root = Path(configured_root) if configured_root else REPOSITORY_ROOT
        manifest = cls.golden_root / "data/manifests/batch_c_feature_matrix_registry_summary.json"
        if not manifest.exists():
            raise unittest.SkipTest("Worktree không chứa official manifests; cần RESEARCH_GOLDEN_ROOT.")

    def test_feature_and_registry_counts_match_baseline(self) -> None:
        manifest_path = self.golden_root / "data/manifests/batch_c_feature_matrix_registry_summary.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["final_matrix_stats"]["row_count"], 307_511)
        self.assertEqual(manifest["final_matrix_stats"]["feature_count"], 166)
        self.assertEqual(manifest["registry_stats"]["feature_registry_entry_count"], 166)
        self.assertEqual(manifest["registry_stats"]["missing_feature_registry_count"], 0)

    def test_model_feature_registry_excludes_target_and_entity_id(self) -> None:
        columns_path = self.golden_root / "ml/registry/model_feature_columns.json"
        feature_columns = json.loads(columns_path.read_text(encoding="utf-8"))
        self.assertEqual(len(feature_columns), 166)
        self.assertNotIn("TARGET", feature_columns)
        self.assertNotIn("SK_ID_CURR", feature_columns)
        self.assertNotIn("SK_ID_BUREAU", feature_columns)
        self.assertNotIn("SK_ID_PREV", feature_columns)

        registry_path = self.golden_root / "ml/registry/feature_registry.csv"
        with registry_path.open("r", encoding="utf-8", newline="") as registry_file:
            registry_rows = list(csv.DictReader(registry_file))
        self.assertEqual(len(registry_rows), 166)


if __name__ == "__main__":
    unittest.main()
