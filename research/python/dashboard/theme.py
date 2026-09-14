"""Visual tokens shared by every dashboard page and Plotly figure."""

from __future__ import annotations

from typing import Final


MODEL_COLORS: Final[dict[str, str]] = {
    "qwen3_8b": "#0F766E",
    "deepseek_v4_flash": "#2563EB",
    "phi4_mini_instruct": "#7C3AED",
}

MODEL_LINE_DASH: Final[dict[str, str]] = {
    "qwen3_8b": "solid",
    "deepseek_v4_flash": "solid",
    "phi4_mini_instruct": "solid",
}

TEMPLATE_REFERENCE_COLOR: Final[str] = "#52525B"

STATUS_COLORS: Final[dict[str, str]] = {
    "ready": "#067647",
    "information": "#175CD3",
    "warning": "#B54708",
    "critical": "#B42318",
    "neutral": "#667085",
}

# Deliberately discrete performance bands. Repeated stops prevent a smooth
# rainbow-like interpolation that could imply more precision than the display
# contract intends.
E2E_DISCRETE_COLORSCALE: Final[list[list[float | str]]] = [
    [0.0000, "#9B1C1C"],
    [0.6999, "#9B1C1C"],
    [0.7000, "#C2410C"],
    [0.7999, "#C2410C"],
    [0.8000, "#A16207"],
    [0.8999, "#A16207"],
    [0.9000, "#0F766E"],
    [0.9499, "#0F766E"],
    [0.9500, "#166534"],
    [1.0000, "#166534"],
]

E2E_BAND_LABELS: Final[tuple[tuple[str, str], ...]] = (
    ("Very high ≥95%", "#166534"),
    ("High 90–<95%", "#0F766E"),
    ("Moderate 80–<90%", "#A16207"),
    ("Low 70–<80%", "#C2410C"),
    ("Critical <70%", "#9B1C1C"),
)

PLOTLY_FONT_FAMILY: Final[str] = (
    "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "
    "'Segoe UI', sans-serif"
)

PLOTLY_CONFIG: Final[dict[str, object]] = {
    "displayModeBar": False,
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": False,
    "modeBarButtonsToRemove": [
        "lasso2d",
        "select2d",
        "autoScale2d",
        "toggleSpikelines",
    ],
    "toImageButtonOptions": {
        "format": "svg",
        "filename": "llm_xai_research_figure",
        "height": 900,
        "width": 1600,
        "scale": 1,
    },
}

DMC_THEME: Final[dict[str, object]] = {
    "primaryColor": "teal",
    "fontFamily": PLOTLY_FONT_FAMILY,
    "headings": {"fontFamily": PLOTLY_FONT_FAMILY},
    "defaultRadius": "md",
}
