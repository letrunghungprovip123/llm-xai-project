"""Regression R5 cho modeling, XAI, IR và evidence exposure."""

from __future__ import annotations

import copy
import json
import os
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from research.ml.evidence_exposure.pipeline import (
    build_evidence_packages,
    ensure_disjoint_source_ids,
)
from research.ml.evidence_exposure.selector import (
    build_concept_grouping,
    compute_entropy,
    fixed_top_features,
    select_by_coverage,
)
from research.ml.modeling.evaluation import ModelEvaluation, select_best_model
from research.ml.modeling.training import TrainedModel
from research.ml.xai.evidence_schema import direction_from_shap_value
from research.ml.xai.shap_explainer import compute_additivity_check


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def make_model(name: str) -> TrainedModel:
    return TrainedModel(
        model_name=name,
        model_family="fixture",
        dataset_branch="tree",
        estimator="fixture",
        feature_columns=["feature"],
        training_seconds=0.0,
        train_rows=4,
        feature_count=1,
        metadata={},
    )


def make_evaluation(name: str, average_precision: float, roc_auc: float, brier: float) -> ModelEvaluation:
    return ModelEvaluation(
        model_name=name,
        model_family="fixture",
        dataset_branch="tree",
        split="valid",
        metrics={
            "average_precision": average_precision,
            "roc_auc": roc_auc,
            "brier_score": brier,
        },
        predictions=pd.DataFrame(),
    )


class ModelingPolicyTests(unittest.TestCase):
    def test_selection_uses_average_precision_then_auc_then_lower_brier(self) -> None:
        models = [make_model("a"), make_model("b"), make_model("hist_gradient_boosting")]
        evaluations = [
            make_evaluation("a", 0.27, 0.79, 0.18),
            make_evaluation("b", 0.28, 0.77, 0.20),
            make_evaluation("hist_gradient_boosting", 0.28, 0.78, 0.19),
        ]
        winner, _ = select_best_model(trained_models=models, valid_evaluations=evaluations)
        self.assertEqual(winner.model_name, "hist_gradient_boosting")

        tied_evaluations = [
            make_evaluation("a", 0.28, 0.78, 0.18),
            make_evaluation("b", 0.28, 0.78, 0.20),
        ]
        tied_winner, _ = select_best_model(
            trained_models=models[:2],
            valid_evaluations=tied_evaluations,
        )
        self.assertEqual(tied_winner.model_name, "a")


class XAIInvariantTests(unittest.TestCase):
    def test_shap_direction_and_additivity_keep_sign(self) -> None:
        self.assertEqual(direction_from_shap_value(0.2), "increases_risk")
        self.assertEqual(direction_from_shap_value(-0.2), "decreases_risk")
        self.assertEqual(direction_from_shap_value(1e-13), "neutral")

        errors, passed = compute_additivity_check(
            base_values=np.array([0.2, 0.1]),
            shap_values=np.array([[0.1, 0.2], [0.4, -0.1]]),
            model_outputs=np.array([0.5, 0.5]),
            tolerance=1e-9,
        )
        np.testing.assert_allclose(errors, np.array([0.0, 0.1]))
        self.assertEqual(passed.tolist(), [True, False])

    def test_fixed_and_adaptive_selection_use_absolute_shap_order(self) -> None:
        features = [
            {"feature_id": "a", "shap_value": 0.5, "concept": "c1"},
            {"feature_id": "b", "shap_value": -0.3, "concept": "c1"},
            {"feature_id": "c", "shap_value": 0.15, "concept": "c2"},
            {"feature_id": "d", "shap_value": 0.05, "concept": "c2"},
        ]
        fixed = fixed_top_features(features, top_k=2)
        adaptive = select_by_coverage(features, threshold=0.75, k_min=1, k_max=4)
        self.assertEqual([item["feature_id"] for item in fixed], ["a", "b"])
        self.assertEqual(adaptive["selected_feature_ids"], ["a", "b"])
        self.assertEqual(adaptive["coverage_status"], "PASSED")

    def test_entropy_and_concept_grouping_preserve_mixed_directions(self) -> None:
        selected = [
            {"feature_id": "a", "abs_shap_value": 0.4, "concept": "credit", "direction": "increase_risk"},
            {"feature_id": "b", "abs_shap_value": 0.3, "concept": "credit", "direction": "decrease_risk"},
            {"feature_id": "c", "abs_shap_value": 0.3, "concept": "income", "direction": "increase_risk"},
        ]
        entropy = compute_entropy(selected)
        grouping = build_concept_grouping(selected)
        self.assertEqual(entropy["entropy_level"], "high")
        self.assertEqual(grouping["unique_concept_count"], 2)
        self.assertEqual(grouping["mixed_concept_groups"][0]["concept"], "credit")


class EvidencePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configured_root = os.environ.get("RESEARCH_GOLDEN_ROOT")
        cls.golden_root = Path(configured_root) if configured_root else REPOSITORY_ROOT
        cls.ir_path = (
            cls.golden_root
            / "data/reports/explanation_ir_v2/evaluation/explanation_ir_v2.jsonl"
        )
        if not cls.ir_path.exists():
            raise unittest.SkipTest("Worktree không chứa official IR; cần RESEARCH_GOLDEN_ROOT.")

    def test_one_ir_builds_six_ordered_packages_with_current_semantics(self) -> None:
        with self.ir_path.open("r", encoding="utf-8") as ir_file:
            first_ir = json.loads(ir_file.readline())
        packages = build_evidence_packages([copy.deepcopy(first_ir)], "evaluation")
        self.assertEqual([item["evidence_level"] for item in packages], ["S0", "S1", "S2", "S3", "S4", "S5"])
        self.assertTrue(all(item["evidence_package_schema_version"] == "2.1" for item in packages))
        self.assertEqual(len(packages[0]["selected_evidence"]), 0)
        self.assertEqual(len(packages[1]["selected_evidence"]), 10)

        s1_ids = [item["feature_id"] for item in packages[1]["selected_evidence"]]
        s2_ids = [item["feature_id"] for item in packages[2]["selected_evidence"]]
        s4_ids = [item["feature_id"] for item in packages[4]["selected_evidence"]]
        s5_ids = [item["feature_id"] for item in packages[5]["selected_evidence"]]
        self.assertEqual(s1_ids, s2_ids)
        self.assertEqual(s4_ids, s5_ids)
        self.assertIn("backend_explanation_skeleton", packages[5])

    def test_overlap_guard_rejects_shared_ir_id(self) -> None:
        current = [{"ir_id": "ir-1"}]
        reference = [{"source_ir_id": "ir-1"}]
        with self.assertRaisesRegex(ValueError, "overlap found"):
            ensure_disjoint_source_ids(current, reference)


class OfficialManifestGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configured_root = os.environ.get("RESEARCH_GOLDEN_ROOT")
        cls.golden_root = Path(configured_root) if configured_root else REPOSITORY_ROOT
        manifest = cls.golden_root / "data/manifests/model_training_manifest.json"
        if not manifest.exists():
            raise unittest.SkipTest("Worktree không chứa official manifests; cần RESEARCH_GOLDEN_ROOT.")

    def read_manifest(self, filename: str) -> dict:
        return json.loads((self.golden_root / "data/manifests" / filename).read_text(encoding="utf-8"))

    def test_model_xai_ir_and_evidence_counts_match_baseline(self) -> None:
        model = self.read_manifest("model_training_manifest.json")
        xai = self.read_manifest("xai_evidence_manifest.json")
        ir = self.read_manifest("explanation_ir_v2_manifest_evaluation.json")
        evidence = self.read_manifest("evidence_exposure_manifest_evaluation.json")

        self.assertEqual(model["best_model"]["model_name"], "hist_gradient_boosting")
        self.assertEqual(xai["model"]["feature_count"], 213)
        self.assertEqual(xai["xai_method"]["case_count"], 120)
        self.assertEqual(ir["build_summary"]["ir_record_count"], 120)
        self.assertEqual(evidence["input"]["ir_record_count"], 120)
        self.assertEqual(evidence["output_package_count"], 720)
        self.assertEqual(
            {level: item["record_count"] for level, item in evidence["split_outputs"].items()},
            {level: 120 for level in ["S0", "S1", "S2", "S3", "S4", "S5"]},
        )

    def test_evaluation_subset_keeps_216_packages(self) -> None:
        subset_path = next(self.golden_root.rglob("evidence_packages_36.jsonl"))
        with subset_path.open("r", encoding="utf-8") as subset_file:
            record_count = sum(1 for line in subset_file if line.strip())
        self.assertEqual(record_count, 216)


if __name__ == "__main__":
    unittest.main()
