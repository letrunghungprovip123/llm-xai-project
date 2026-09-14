"""CLI mỏng cho stage audit dữ liệu thô."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy audit và trả exit code."""

    parser = argparse.ArgumentParser(description="Kiểm tra raw data và quan hệ khóa.")
    parser.parse_args(argv)

    from .pipeline import run_data_audit

    run_data_audit()
    path = Path("data/manifests/batch_1_summary.json")
    if not path.is_file():
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    statuses = {item.get("status") for item in payload.get("step_statuses", [])}
    return 0 if statuses == {"raw_verified", "schema_audit_passed", "relationship_audit_passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
