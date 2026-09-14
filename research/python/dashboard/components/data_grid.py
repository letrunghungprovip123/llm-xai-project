"""Small Dash AG Grid wrapper for research evidence tables."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import dash_ag_grid as dag
import pandas as pd

from ..i18n import DEFAULT_LOCALE, ag_grid_locale_text, normalize_locale


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.astype(object).where(pd.notna(frame), None)
    return clean.to_dict("records")


def data_grid(
    *,
    grid_id: str,
    frame: pd.DataFrame,
    column_defs: Sequence[dict[str, Any]],
    height: int = 380,
    page_size: int = 12,
    class_name: str = "research-data-grid",
    locale: object = DEFAULT_LOCALE,
):
    """Render a restrained sortable/filterable evidence table."""

    resolved_locale = normalize_locale(locale)
    return dag.AgGrid(
        id=grid_id,
        rowData=_records(frame),
        columnDefs=list(column_defs),
        defaultColDef={
            "sortable": True,
            "filter": True,
            "resizable": True,
            "minWidth": 90,
        },
        dashGridOptions={
            "pagination": True,
            "paginationPageSize": page_size,
            "paginationPageSizeSelector": False,
            "animateRows": False,
            "suppressCellFocus": True,
            "ensureDomOrder": True,
            "localeText": ag_grid_locale_text(resolved_locale),
        },
        columnSize="sizeToFit",
        className=f"ag-theme-quartz {class_name}",
        style={"height": f"{height}px", "width": "100%"},
    )
