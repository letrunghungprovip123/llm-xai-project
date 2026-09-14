"""CLI mỏng cho stage audit TARGET, missing values và anomaly."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy audit và trả exit code."""

    parser = argparse.ArgumentParser(description="Kiểm tra target, missing và anomaly.")
    parser.parse_args(argv)

    from .pipeline import run_target_audit

    run_target_audit()
    path = Path("data/manifests/batch_a2_target_missing_audit_summary.json")
    if not path.is_file():
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    return 0 if payload.get("pipeline_group_status") == "raw_audit_layer_completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
