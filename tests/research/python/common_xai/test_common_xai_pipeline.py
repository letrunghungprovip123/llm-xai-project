from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from research.python.common_xai.context import CommonXAIRunContext
from research.python.common_xai.evidence_stage import run_common_evidence
from research.python.common_xai.ir_stage import run_common_ir
from research.python.common_xai.xai_stage import select_common_cases
from research.python.xai.loaders import XAIModelBundle




@pytest.fixture(autouse=True)
def _parquet_engine_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def write_pickle(self: pd.DataFrame, path, index: bool = False, **kwargs) -> None:
        frame = self.reset_index(drop=True) if not index else self
        frame.to_pickle(path)

    def read_pickle(path, **kwargs) -> pd.DataFrame:
        return pd.read_pickle(path)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", write_pickle)
    monkeypatch.setattr(pd, "read_parquet", read_pickle)


class _Estimator:
    pass


def _ctx(tmp_path: Path, dataset_id: str = "credit_dataset_c") -> CommonXAIRunContext:
    from research.python.common.hashing import sha256_file
    from research.python.datasets.profile import sha256_json

    source_root = tmp_path / "source"
    (source_root / "data").mkdir(parents=True)
    feature = source_root / "data" / "feature.parquet"
    target = source_root / "data" / "target.parquet"
    feature.write_bytes(b"feature")
    target.write_bytes(b"target")
    reg_csv = source_root / "feature_registry.csv"
    reg_csv.write_text("feature_name,concept\nf1,credit_history\n", encoding="utf-8")
    reg_yaml = source_root / "feature_registry.yaml"
    reg_yaml.write_text("schema_version: fixture\nfeatures: {}\n", encoding="utf-8")
    concept = source_root / "concept_registry.yaml"
    concept.write_text("schema_version: fixture\nconcepts: {}\n", encoding="utf-8")
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
            "prediction_semantics": {
                "positive_label": "high_12m_default_risk",
                "negative_label": "low_12m_default_risk",
                "prediction_subject": "rủi ro vỡ nợ trong 12 tháng",
                "positive_display_name": "rủi ro vỡ nợ trong 12 tháng cao",
                "negative_display_name": "rủi ro vỡ nợ trong 12 tháng thấp",
                "positive_direction_phrase": "rủi ro cao",
                "negative_direction_phrase": "rủi ro thấp",
            },
        },
        "adapter": {"adapter_id": "fixture", "adapter_version": "v1"},
        "capabilities": {
            "supports_stratified_split": True,
            "supports_feature_level_xai": True,
            "supports_semantic_registry": True,
            "supports_case_strata": True,
            "supports_adaptive_evidence": True,
            "has_stable_entity_id": True,
            "feature_count": 6,
        },
    }
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    refs = {
        "feature_matrix": feature,
        "target": target,
        "feature_registry_csv": reg_csv,
        "feature_registry_yaml": reg_yaml,
        "concept_registry_yaml": concept,
    }
    bundle = {
        "schema_version": "canonical_dataset_bundle_v1",
        "dataset_id": dataset_id,
        "dataset_version": "v1",
        "dataset_fingerprint": "b" * 64,
        "dataset_profile_sha256": sha256_json(profile),
        "artifacts": {
            name: {"path": str(path), "sha256": sha256_file(path), "required": True}
            for name, path in refs.items()
        },
        "provenance": {"artifact_source_root_locator": str(source_root)},
    }
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()

    # Satisfy the source-ML completion contract without creating real model data.
    source_workspace = project / ".researchops/workspaces" / dataset_id / "replication_v1" / "ml-run"
    for directory in (
        source_workspace / "data/manifests",
        source_workspace / "data/reports",
        source_workspace / "ml/registry",
        source_workspace / "artifacts/models",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (source_workspace / "data/manifests/common_ml_model_training_manifest.json").write_text("{}", encoding="utf-8")
    (source_workspace / "artifacts/models/best_model.joblib").write_bytes(b"placeholder")
    (source_workspace / "ml/registry/model_registry.json").write_text("{}", encoding="utf-8")
    (source_workspace / "data/reports/model_predictions_test.csv").write_text("case_id\n", encoding="utf-8")

    return CommonXAIRunContext.load(
        dataset_profile_path=profile_path,
        canonical_bundle_path=bundle_path,
        experiment_id="replication_v1",
        source_run_id="ml-run",
        run_id="xai-run",
        project_root=project,
    )


def test_common_case_selection_uses_dataset_scoped_string_identity(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    predictions = pd.DataFrame(
        [
            ["case-credit_dataset_c-borrower-A", "A", 0, 1, 0.95, 1],
            ["case-credit_dataset_c-borrower-B", "B", 1, 0, 0.85, 1],
            ["case-credit_dataset_c-borrower-C", "C", 2, 1, 0.45, 0],
            ["case-credit_dataset_c-borrower-D", "D", 3, 0, 0.10, 0],
            ["case-credit_dataset_c-borrower-E", "E", 4, 0, 0.51, 1],
            ["case-credit_dataset_c-borrower-F", "F", 5, 1, 0.49, 0],
            ["case-credit_dataset_c-borrower-G", "G", 6, 0, 0.02, 0],
            ["case-credit_dataset_c-borrower-H", "H", 7, 1, 0.99, 1],
        ],
        columns=["case_id", "source_entity_id", "row_index", "y_true", "y_proba", "y_pred_default_threshold_0_5"],
    )
    model = XAIModelBundle(
        bundle={}, estimator=_Estimator(), feature_columns=["f1"], model_name="random_forest",
        model_version="v1", model_family="tree", dataset_branch="tree", default_threshold=0.5, feature_count=1,
    )
    selected, counts, _ = select_common_cases(
        ctx=ctx, model_bundle=model, predictions=predictions, cases_per_group=1
    )
    assert set(counts) == {"top_high_risk", "low_risk", "true_positive", "false_positive", "false_negative", "near_threshold"}
    assert selected["case_id"].is_unique
    assert selected["evidence_id"].is_unique
    assert all("credit_dataset_c" in value for value in selected["evidence_id"])
    assert "SK_ID_CURR" not in selected.columns


def _seed_common_xai_artifacts(ctx: CommonXAIRunContext) -> None:
    ctx.create_workspace()
    (ctx.paths.manifest_dir / "common_xai_manifest.json").write_text("{}", encoding="utf-8")
    evidence_id = "xai::credit_dataset_c::replication_v1::hgb::v1::case-C-1::top_high_risk"
    factors = []
    shap_values = [0.30, -0.20, 0.12, -0.08, 0.06, -0.04]
    for rank, value in enumerate(shap_values, start=1):
        factors.append(
            {
                "rank": rank,
                "feature_name": f"feature_{rank}",
                "raw_feature_name": f"raw_{rank}",
                "display_name": f"Feature {rank}",
                "concept": "credit_history" if rank <= 3 else "financial_capacity",
                "feature_value": float(rank),
                "shap_value": value,
                "abs_shap_value": abs(value),
                "direction": "increases_risk" if value > 0 else "decreases_risk",
                "contribution_percent_of_top_k_abs": None,
                "metadata": {
                    "mapping_found": True,
                    "feature_registry": {
                        "feature_name": f"raw_{rank}",
                        "display_name": f"Feature {rank}",
                        "concept": "credit_history" if rank <= 3 else "financial_capacity",
                        "value_type": "numeric",
                        "allowed_in_user_explanation": True,
                    },
                },
            }
        )
    record = {
        "evidence_id": evidence_id,
        "created_at": "2026-08-12T00:00:00+00:00",
        "model": {"model_name": "hist_gradient_boosting", "model_version": "v1", "model_family": "tree_boosting", "dataset_branch": "tree", "feature_count": 6},
        "case": {"case_id": "case-credit_dataset_c-borrower-C-1", "source_entity_id": "C-1", "entity_type": "borrower", "row_index": 0, "case_type": "top_high_risk", "selection_rank": 1},
        "prediction": {"y_true": 1, "y_proba": 0.8, "y_pred": 1, "threshold": 0.5, "predicted_label_text": "high_default_risk", "true_label_text": "high_default_risk"},
        "shap": {"base_value": 0.64, "model_output": 0.8, "shap_sum": 0.16, "reconstructed_output": 0.8, "additivity_error": 0.0, "output_space": "probability", "positive_class": 1, "xai_method": "SHAP", "explainer_type": "TreeExplainer"},
        "local_features": factors,
        "quality": {"top_k": 6, "feature_count": 6, "local_feature_count": 6, "positive_feature_count": 3, "negative_feature_count": 3, "neutral_feature_count": 0, "mapping_missing_count": 0, "passed_additivity_check": True, "additivity_tolerance": 0.01},
        "metadata": {"row_index": 0, "case_type": "top_high_risk", "selection_rank": 1},
    }
    xai_dir = ctx.paths.report_dir / "xai"
    xai_dir.mkdir(parents=True, exist_ok=True)
    (xai_dir / "xai_local_evidence.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    quality_dir = ctx.paths.report_dir / "xai_quality"
    quality_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {
            "evidence_id": evidence_id, "additivity_error": 0.0, "additivity_error_abs": 0.0, "additivity_pass": True,
            "top3_coverage": 0.72, "top5_coverage": 0.95, "top10_coverage": 1.0, "top20_coverage": 1.0,
            "positive_shap_sum": 0.48, "negative_shap_sum": -0.32, "positive_abs_share": 0.6, "negative_abs_share": 0.4,
            "top_positive_feature_count": 3, "top_negative_feature_count": 3, "neutral_feature_count": 0,
            "concept_sum_error": 0.0, "concept_sum_error_abs": 0.0, "concept_coverage_top3": 1.0,
            "unknown_feature_group_count": 0, "unknown_feature_group_abs_share": 0.0,
            "top1_concept": "credit_history", "top3_concepts": "credit_history|financial_capacity",
            "comprehensiveness_top5": 0.1, "comprehensiveness_top10": 0.1,
            "sufficiency_drop_top5": 0.02, "sufficiency_drop_top10": 0.02,
            "stability_status": "skipped", "stability_score": None,
        }
    ]).to_csv(quality_dir / "xai_evidence_quality_summary.csv", index=False)
    pd.DataFrame([
        {"evidence_id": evidence_id, "concept_group": "credit_history", "concept_rank": 1, "concept_shap_value": 0.22, "concept_abs_shap": 0.62, "concept_direction": "increases_risk", "feature_count_in_concept": 3, "top_features_in_concept": "Feature 1|Feature 2|Feature 3"},
        {"evidence_id": evidence_id, "concept_group": "financial_capacity", "concept_rank": 2, "concept_shap_value": -0.06, "concept_abs_shap": 0.18, "concept_direction": "decreases_risk", "feature_count_in_concept": 3, "top_features_in_concept": "Feature 4|Feature 5|Feature 6"},
    ]).to_csv(quality_dir / "xai_concept_aggregation_report.csv", index=False)


def test_ir_v3_and_s0_s5_are_dataset_aware_without_changing_evidence_policy(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _seed_common_xai_artifacts(ctx)
    ir = run_common_ir(ctx)
    assert ir.record_count == 1
    ir_record = json.loads(ir.ir_path.read_text(encoding="utf-8").strip())
    assert ir_record["ir_schema_version"] == "explanation_ir_v3"
    assert ir_record["dataset"]["dataset_id"] == "credit_dataset_c"
    assert ir_record["case"]["case_id"] == "case-credit_dataset_c-borrower-C-1"
    assert ir_record["target_semantics"]["prediction_horizon"] == "12_months"
    assert ir_record["prediction_summary"]["predicted_label"] == "high_12m_default_risk"
    assert ir_record["target_semantics"]["positive_label"] == "high_12m_default_risk"
    assert "SK_ID_CURR" not in ir_record["case"]

    evidence = run_common_evidence(ctx)
    assert evidence.package_count == 6
    packages = [json.loads(line) for line in evidence.packages_path.read_text(encoding="utf-8").splitlines() if line]
    by_level = {item["evidence_level"]: item for item in packages}
    assert set(by_level) == {"S0", "S1", "S2", "S3", "S4", "S5"}
    assert by_level["S0"]["selected_evidence"] == []
    assert [x["feature_id"] for x in by_level["S1"]["selected_evidence"]] == [x["feature_id"] for x in by_level["S2"]["selected_evidence"]]
    assert [x["shap_value"] for x in by_level["S4"]["selected_evidence"]] == [x["shap_value"] for x in by_level["S5"]["selected_evidence"]]
    assert all(item["dataset"]["dataset_id"] == "credit_dataset_c" for item in packages)
    assert all(item["case"]["case_id"] == "case-credit_dataset_c-borrower-C-1" for item in packages)
    assert all(item["prompt_payload"]["target_semantics"]["positive_label"] == "high_12m_default_risk" for item in packages)
    assert all(item["prompt_payload"]["target_semantics"]["prediction_subject"] == "rủi ro vỡ nợ trong 12 tháng" for item in packages)
    assert all("source_positive_value" not in item["prompt_payload"]["target_semantics"] for item in packages)
    assert all("credit_dataset_c" in item["package_id"] for item in packages)


def test_common_xai_source_has_no_home_credit_identity_dependency() -> None:
    root = Path(__file__).resolve().parents[4]
    common_xai = root / "research/python/common_xai"
    source = "\n".join(path.read_text(encoding="utf-8") for path in common_xai.glob("*.py"))
    assert "SK_ID_CURR" not in source
    assert "SK_ID_BUREAU" not in source
    assert "SK_ID_PREV" not in source


def test_common_xai_runs_real_shap_on_non_home_credit_common_ml_fixture(tmp_path: Path) -> None:
    from tests.research.python.common_ml.test_common_ml_pipeline import _make_fixture
    from research.python.common_ml.split import run_common_split
    from research.python.common_ml.preprocessing import run_common_preprocessing
    from research.python.common_ml.modeling import run_common_modeling
    from research.python.common_xai.xai_stage import run_common_xai

    ml_ctx = _make_fixture(tmp_path, dataset_id="third_credit_dataset_fixture")
    run_common_split(ml_ctx)
    run_common_preprocessing(ml_ctx)
    run_common_modeling(ml_ctx)
    xai_ctx = CommonXAIRunContext.load(
        dataset_profile_path=ml_ctx.dataset_profile_path,
        canonical_bundle_path=ml_ctx.canonical_bundle_path,
        experiment_id=ml_ctx.experiment_id,
        source_run_id=ml_ctx.run_id,
        run_id="xai-real-shap",
        project_root=ml_ctx.project_root,
        artifact_root=ml_ctx.artifact_root,
    )
    result = run_common_xai(xai_ctx, cases_per_group=1)
    assert result.case_count > 0
    assert result.feature_count >= 6
    assert result.failed_additivity_count == 0
    assert result.explainer_type in {"TreeExplainer", "PermutationExplainer"}
    evidence_lines = [line for line in result.evidence_path.read_text(encoding="utf-8").splitlines() if line]
    evidence = json.loads(evidence_lines[0])
    assert evidence["case"]["case_id"].startswith("case_third_credit_dataset_fixture_borrower_")
    assert evidence["metadata"]["dataset_id"] == "third_credit_dataset_fixture"

    ir = run_common_ir(xai_ctx)
    packages = run_common_evidence(xai_ctx)
    assert ir.record_count == result.case_count
    assert packages.package_count == result.case_count * 6
