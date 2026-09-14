"""CLI mỏng cho feature engineering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy pipeline và trả exit code."""

    parser = argparse.ArgumentParser(description="Xây các customer-level feature group.")
    parser.parse_args(argv)

    from .pipeline import run_feature_engineering

    run_feature_engineering()
    path = Path("data/manifests/batch_b_feature_engineering_summary.json")
    if not path.is_file():
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    return 0 if payload.get("pipeline_group_status") == "feature_engineering_layer_completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
