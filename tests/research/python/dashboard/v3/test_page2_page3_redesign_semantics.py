from pathlib import Path


EFFECTIVENESS = Path("research/python/dashboard/v3/pages/effectiveness.py")
MECHANISMS = Path("research/python/dashboard/v3/pages/mechanisms.py")
CALLBACKS = Path("research/python/dashboard/v3/callbacks.py")
CSS = Path("research/python/dashboard/assets/app.css")


def test_effectiveness_design_lock_is_present():
    source = EFFECTIVENESS.read_text(encoding="utf-8")
    for token in (
        "Reliability Map",
        "Evidence Response Profiles",
        "Option × Metric matrix",
        "Major Effects",
        "Contrast Effect Plot",
        "Primary performance",
        "Secondary metrics",
        "Statistical evidence",
        "Major Effects vẫn là full-study tests",
    ):
        assert token in source
    assert "Replication status" not in source
    assert "material_heterogeneity" not in source


def test_mechanisms_design_lock_is_present_and_noncausal():
    source = MECHANISMS.read_text(encoding="utf-8")
    for token in (
        "100% Faithfulness Accounting",
        "Claim type × Validation status",
        "Verifiability × Resolved Faithfulness Map",
        "Loss decomposition",
        "Claim diagnostics",
        "Quality mechanisms",
        "không causal attribution",
        "N/A khác 0",
        "presentation normalization",
    ):
        assert token in source


def test_callbacks_only_select_filter_and_reshape_certified_rows():
    source = CALLBACKS.read_text(encoding="utf-8")
    for forbidden in ("scipy", "statsmodels", "wilcoxon", "multipletests", "bootstrap("):
        assert forbidden not in source
    assert "effectiveness_descriptive_views" in source
    assert "mechanisms_claim_matrix" in source
    assert "mechanisms_quality_map" in source


def test_plotly_hosts_are_crop_safe_and_responsive_breakpoints_exist():
    source = CSS.read_text(encoding="utf-8")
    assert ".analysis-chart__graph" in source
    assert "overflow: visible" in source
    assert "@media (max-width: 1180px)" in source
    assert "@media (max-width: 820px)" in source


def test_runtime_tabs_use_shell_proven_primitive_and_keep_all_callback_targets_mounted():
    effectiveness = EFFECTIVENESS.read_text(encoding="utf-8")
    mechanisms = MECHANISMS.read_text(encoding="utf-8")
    callbacks = CALLBACKS.read_text(encoding="utf-8")

    # 0047 runtime compatibility gate: both blank pages were the only v3 pages
    # using dmc.Tabs/TabsPanel. Use the shell-proven SegmentedControl and keep
    # all three analytical panel divs mounted so hidden-tab graph callbacks
    # always have a target in the DOM.
    assert "dmc.Tabs(" not in effectiveness
    assert "dmc.TabsPanel(" not in effectiveness
    assert "dmc.Tabs(" not in mechanisms
    assert "dmc.TabsPanel(" not in mechanisms
    assert "dmc.SegmentedControl(" in effectiveness
    assert "dmc.SegmentedControl(" in mechanisms

    for token in (
        "effectiveness-tab-primary-panel",
        "effectiveness-tab-secondary-panel",
        "effectiveness-tab-statistics-panel",
        "mechanisms-tab-loss-panel",
        "mechanisms-tab-claims-panel",
        "mechanisms-tab-quality-panel",
    ):
        assert token in effectiveness + mechanisms

    assert "def effectiveness_tabs(active_tab)" in callbacks
    assert "def mechanisms_tabs(active_tab)" in callbacks
