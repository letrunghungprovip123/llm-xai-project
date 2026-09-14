from __future__ import annotations

from research.python.datasets.contracts import DatasetProfile
from research.python.datasets.intake import FAIL, PASS, WARN, evaluate_replication_profile


def _profile(*, feature_count: int, explicit_semantics: bool = True) -> DatasetProfile:
    target = {
        "source_column": "bad_24m",
        "canonical_name": "target",
        "positive_value": "Y",
        "negative_value": "N",
        "semantic_name": "serious_delinquency_within_24_months",
        "prediction_horizon": "24_months",
    }
    if explicit_semantics:
        target["prediction_semantics"] = {
            "positive_label": "high_serious_delinquency_risk",
            "negative_label": "low_serious_delinquency_risk",
            "prediction_subject": "rủi ro trễ hạn nghiêm trọng trong 24 tháng",
            "positive_display_name": "rủi ro trễ hạn nghiêm trọng trong 24 tháng cao",
            "negative_display_name": "rủi ro trễ hạn nghiêm trọng trong 24 tháng thấp",
            "positive_direction_phrase": "rủi ro cao",
            "negative_direction_phrase": "rủi ro thấp",
        }
    return DatasetProfile.from_dict(
        {
            "schema_version": "dataset_profile_v1",
            "dataset_id": "dataset_b_fixture",
            "dataset_version": "v1",
            "domain": "credit_risk",
            "task_type": "binary_classification",
            "entity": {"entity_type": "borrower", "source_id_column": "borrower_id"},
            "target": target,
            "adapter": {"adapter_id": "dataset_b", "adapter_version": "v1"},
            "capabilities": {
                "supports_stratified_split": True,
                "supports_feature_level_xai": True,
                "supports_semantic_registry": True,
                "supports_case_strata": True,
                "supports_adaptive_evidence": True,
                "has_stable_entity_id": True,
                "feature_count": feature_count,
            },
        }
    )


def test_replication_profile_passes_for_rich_explicit_dataset() -> None:
    report = evaluate_replication_profile(_profile(feature_count=24))
    assert report.status == PASS
    assert not report.failures


def test_replication_profile_rejects_top10_collapse_and_missing_semantics() -> None:
    report = evaluate_replication_profile(
        _profile(feature_count=8, explicit_semantics=False)
    )
    assert report.status == FAIL
    failure_ids = {item.check_id for item in report.failures}
    assert "feature_richness" in failure_ids
    assert "explicit_target_semantics" in failure_ids


def test_replication_profile_warns_for_borderline_feature_count() -> None:
    report = evaluate_replication_profile(_profile(feature_count=15))
    assert report.status == WARN
    assert any(item.check_id == "feature_richness" for item in report.warnings)
