"""CLI mỏng cho leakage audit và data split."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy split pipeline và trả exit code."""

    parser = argparse.ArgumentParser(description="Audit leakage và tạo train/valid/test split.")
    parser.parse_args(argv)

    from .pipeline import run_data_split

    run_data_split()
    path = Path("data/manifests/batch_d_leakage_split_summary.json")
    if not path.is_file():
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    return 0 if payload.get("pipeline_group_status") == "leakage_split_layer_completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
