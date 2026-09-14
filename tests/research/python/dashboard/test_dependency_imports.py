"""Dashboard dependency smoke tests."""

from __future__ import annotations

from importlib.metadata import version


def test_dashboard_dependencies_are_importable() -> None:
    import dash  # noqa: F401
    import dash_ag_grid  # noqa: F401
    import dash_iconify  # noqa: F401
    import dash_mantine_components  # noqa: F401
    import kaleido  # noqa: F401
    import plotly  # noqa: F401
    import playwright  # noqa: F401


def test_dashboard_dependency_versions() -> None:
    expected = {
        "dash": "4.4.1",
        "plotly": "6.9.0",
        "dash-mantine-components": "2.8.0",
        "dash-ag-grid": "35.3.0",
        "dash-iconify": "0.1.2",
        "kaleido": "1.3.0",
        "playwright": "1.61.0",
        "pytest-playwright": "0.8.0",
    }

    actual = {
        package: version(package)
        for package in expected
    }

    assert actual == expected
