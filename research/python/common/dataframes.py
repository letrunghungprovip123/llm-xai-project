"""Các invariant DataFrame được nhiều stage sử dụng trực tiếp."""

from __future__ import annotations

import numpy as np
import pandas as pd


def replace_infinite_with_nan(frame: pd.DataFrame) -> pd.DataFrame:
    """Chuẩn hóa giá trị vô cực trước khi validate hoặc ghi artifact."""

    return frame.replace([np.inf, -np.inf], np.nan)


def count_infinite_values(frame: pd.DataFrame) -> int:
    """Đếm giá trị vô cực chỉ trên các cột số."""

    numeric_frame = frame.select_dtypes(include=[np.number])
    if numeric_frame.empty:
        return 0
    return int(np.isinf(numeric_frame.to_numpy()).sum())
