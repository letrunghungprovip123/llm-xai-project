from pathlib import Path

from research.python.dashboard.v3.figures import (
    overview_major_effects,
    overview_option_landscape,
    overview_validation_composition,
)
from research.python.dashboard.v3.overview_model import build_overview_model
from research.python.dashboard.v3.repository import get_v3_repository


def test_overview_is_vietnamese_only_and_all_headline_values_are_provenanced():
    repo = get_v3_repository()
    for scope in ("HOME_CREDIT", "FREDDIE", "CROSS_DATASET"):
        model = build_overview_model(repo, scope, "en")  # old callers cannot revive EN UI
        assert model.scope == scope
        assert model.locale == "vi"
        assert model.title == "Tổng quan nghiên cứu"
        assert len(model.cards) == 4
        assert all(value.report_number_id for card in model.cards for value in card.values)


def test_cross_dataset_overview_is_comparative_not_pooled():
    model = build_overview_model(get_v3_repository(), "CROSS_DATASET", "vi")
    assert all(len(card.values) == 2 for card in model.cards)
    assert {value.dataset_scope for card in model.cards for value in card.values} == {"HOME_CREDIT", "FREDDIE"}
    assert len(model.option_rows) == 18
    assert len(model.effects) == 3
    assert len(model.validation_rows) == 2
    assert {row["dataset_scope"] for row in model.validation_rows} == {"HOME_CREDIT", "FREDDIE"}
    assert model.robust_recommendation_status == "NO_ROBUST_RECOMMENDATION"
    assert model.replication_scope == "MODEL_REVISION_UNKNOWN"
    assert model.rank_stability is not None
    assert sum(int(row["count"]) for row in model.replication_counts) == 33


def test_study_overview_keeps_primary_lane_and_18_option_topology():
    repo = get_v3_repository()
    for scope in ("HOME_CREDIT", "FREDDIE"):
        model = build_overview_model(repo, scope, "vi")
        assert len(model.cards) == 4
        assert all(card.analysis_lane == "PRIMARY" for card in model.cards)
        assert all(len(card.values) == 1 for card in model.cards)
        assert len(model.option_rows) == 18
        assert len(model.effects) == 3
        assert len(model.validation_rows) == 1


def test_overview_source_has_no_science_engine_or_versioned_product_copy():
    paths = [
        Path("research/python/dashboard/v3/overview_model.py"),
        Path("research/python/dashboard/v3/pages/overview.py"),
        Path("research/python/dashboard/v3/figures.py"),
    ]
    forbidden = (
        "scipy",
        "statsmodels",
        "wilcoxon",
        "bootstrap(",
        "multipletests",
        "get_dashboard_repository",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source


def test_product_shell_has_no_language_selector_and_no_visible_version_branding():
    shell = Path("research/python/dashboard/v3/shell.py").read_text(encoding="utf-8")
    app = Path("research/python/dashboard/app_v3.py").read_text(encoding="utf-8")
    assert "dmc.SegmentedControl(id=LOCALE_SELECT" not in shell
    assert 'storage_type="memory"' in shell
    assert "LLM–XAI Research Dashboard" in shell
    assert 'title="LLM–XAI Research Dashboard"' in app


def test_overview_figures_are_compact_crop_safe_and_cross_dataset_heatmaps_share_scale():
    repo = get_v3_repository()
    for scope in ("HOME_CREDIT", "FREDDIE", "CROSS_DATASET"):
        model = build_overview_model(repo, scope, "vi")
        landscape = overview_option_landscape(model.option_rows, cross_dataset=scope == "CROSS_DATASET")
        effects = overview_major_effects(model.effects, cross_dataset=scope == "CROSS_DATASET")
        validation = overview_validation_composition(model.validation_rows)
        assert int(landscape.layout.height) <= 380
        assert int(effects.layout.height) <= 290
        assert int(validation.layout.height) <= 260
        assert tuple(effects.layout.yaxis.categoryarray) == ("Model", "Evidence", "Model × Evidence")
        assert float(validation.layout.legend.y) > 1.0
        if scope == "CROSS_DATASET":
            heatmaps = [trace for trace in landscape.data if trace.type == "heatmap"]
            assert len(heatmaps) == 2
            assert all(float(trace.zmin) == 0.0 and float(trace.zmax) == 1.0 for trace in heatmaps)
            labels = {str(item.text).replace("<b>", "").replace("</b>", "") for item in landscape.layout.annotations}
            assert labels == {"Home Credit", "Freddie Mac"}


def test_overview_shell_generic_copy_is_vietnamese_while_scientific_terms_stay_intact():
    shell = Path("research/python/dashboard/v3/shell.py").read_text(encoding="utf-8")
    page = Path("research/python/dashboard/v3/pages/overview.py").read_text(encoding="utf-8")
    assert "Phân tích nghiên cứu multi-dataset" in shell
    assert '"Xuất"' in shell
    assert "Dữ liệu đã chứng nhận" in shell
    assert "Phạm vi nghiên cứu" in page
    assert "Phân tích chuyên sâu" in page
    assert "End-to-End Faithfulness" in page
    assert "Partial η²" in page
    for generic_english in ("Multi-dataset analytical research", "Study scope", "Explore deeper", "Research overview"):
        assert generic_english not in shell + page
