from pathlib import Path

import numpy as np

from research.python.dashboard.v3.effectiveness_model import build_effectiveness_model
from research.python.dashboard.v3.figures import (
    effectiveness_contrast_plot,
    effectiveness_effect_size_plot,
    effectiveness_evidence_profiles,
    effectiveness_metric_matrix,
    effectiveness_reliability_map,
    mechanism_claim_matrix,
    mechanism_faithfulness_accounting,
    mechanism_lexical_signal,
    mechanism_quality_map,
)
from research.python.dashboard.v3.mechanisms_model import build_mechanisms_model
from research.python.dashboard.v3.repository import get_v3_repository


def test_effectiveness_has_certified_topology_for_every_scope():
    repo = get_v3_repository()
    for scope in ("HOME_CREDIT", "FREDDIE"):
        model = build_effectiveness_model(repo, scope, "vi")
        assert len(model.option_rows) == 18
        assert len(model.secondary_metric_rows) == 72
        assert len(model.effect_rows) == 3
        assert len(model.contrast_rows) == 33
        assert model.rank_rows == ()
        assert all(row["mean_e2e_report_number_id"] for row in model.option_rows)

    cross = build_effectiveness_model(repo, "CROSS_DATASET", "vi")
    assert len(cross.option_rows) == 36
    assert {row["dataset_scope"] for row in cross.option_rows} == {"HOME_CREDIT", "FREDDIE"}
    assert len(cross.secondary_metric_rows) == 144
    assert len(cross.effect_rows) == 6
    assert len(cross.contrast_rows) == 66
    assert cross.rank_rows == ()


def test_effectiveness_figures_preserve_shared_scales_and_certified_counts():
    repo = get_v3_repository()
    cross = build_effectiveness_model(repo, "CROSS_DATASET", "vi")
    reliability = effectiveness_reliability_map(cross.option_rows, cross_dataset=True)
    profiles = effectiveness_evidence_profiles(cross.option_rows, cross_dataset=True)
    matrix = effectiveness_metric_matrix(cross.secondary_metric_rows, cross_dataset=True)
    effects = effectiveness_effect_size_plot(cross.effect_rows, cross_dataset=True)
    contrasts = effectiveness_contrast_plot(cross.contrast_rows, cross_dataset=True, family="evidence_vs_s0")

    assert sum(len(trace.x) for trace in reliability.data) == 36
    assert tuple(reliability.layout.xaxis.range) == (0, 1.02)
    assert tuple(reliability.layout.xaxis2.range) == (0, 1.02)
    assert tuple(reliability.layout.yaxis.range) == (0, 1.02)
    assert tuple(reliability.layout.yaxis2.range) == (0, 1.02)
    assert len(profiles.data) == 6
    assert len(matrix.data) == 2
    assert all(float(trace.zmin) == 0.0 and float(trace.zmax) == 1.0 for trace in matrix.data)
    assert len(effects.data) == 2
    assert len(contrasts.data) == 2


def test_mechanisms_never_pool_cross_dataset_claims_and_preserves_causal():
    repo = get_v3_repository()
    cross = build_mechanisms_model(repo, "CROSS_DATASET", "vi")
    assert len(cross.loss_rows) == 2
    assert {row["dataset_scope"] for row in cross.loss_rows} == {"HOME_CREDIT", "FREDDIE"}
    for row in cross.loss_rows:
        total = sum(float(row[key]) for key in ("primary_e2e", "pipeline_loss", "not_verifiable_loss", "unsupported_loss", "contradiction_loss"))
        assert np.isclose(total, 1.0, atol=1e-8)

    source_types = set(repo.table("claim_type_profile")["claim_type"].astype(str))
    rendered_types = {str(row["claim_type"]) for row in cross.claim_rows}
    assert rendered_types == source_types
    assert "causal" in rendered_types
    assert len(cross.quality_rows) == 36
    assert cross.reason_profile_status == "NOT_AVAILABLE_IN_VISUALIZATION_DATA_V3"


def test_mechanisms_figures_are_diagnostic_and_do_not_pool_studies():
    repo = get_v3_repository()
    cross = build_mechanisms_model(repo, "CROSS_DATASET", "vi")
    accounting = mechanism_faithfulness_accounting(cross.loss_rows)
    lexical = mechanism_lexical_signal(cross.loss_rows)
    claims = mechanism_claim_matrix(cross.claim_rows, cross_dataset=True, measure="share")
    quality = mechanism_quality_map(cross.quality_rows, cross_dataset=True)

    assert len(accounting.data) == 5
    stacked = np.sum([np.asarray(trace.x, dtype=float) for trace in accounting.data], axis=0)
    assert np.allclose(stacked, 1.0, atol=1e-8)
    assert len(lexical.data) == 2
    assert len(claims.data) == 2
    assert all(float(trace.zmin) == 0.0 and float(trace.zmax) == 1.0 for trace in claims.data)
    assert len(quality.data) == 6
    assert tuple(quality.layout.xaxis.range) == (0, 1.02)
    assert tuple(quality.layout.xaxis2.range) == (0, 1.02)


def test_cross_claim_matrix_uses_na_not_zero_for_absent_claim_type():
    repo = get_v3_repository()
    cross = build_mechanisms_model(repo, "CROSS_DATASET", "vi")
    figure = mechanism_claim_matrix(cross.claim_rows, cross_dataset=True, measure="share")
    hc = figure.data[0]
    causal_index = list(hc.y).index("causal")
    assert all(value is None or (isinstance(value, float) and np.isnan(value)) for value in list(hc.z[causal_index]))


def test_redesigned_pages_have_no_scientific_engine_or_v2_fallback():
    paths = [
        Path("research/python/dashboard/v3/effectiveness_model.py"),
        Path("research/python/dashboard/v3/mechanisms_model.py"),
        Path("research/python/dashboard/v3/pages/effectiveness.py"),
        Path("research/python/dashboard/v3/pages/mechanisms.py"),
        Path("research/python/dashboard/v3/figures.py"),
    ]
    forbidden = (
        "scipy",
        "statsmodels",
        "wilcoxon",
        "f_oneway",
        "multipletests",
        "visualization_v2",
        "get_dashboard_repository",
        "replication_status",
        "material_heterogeneity",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{token} leaked into {path}"
