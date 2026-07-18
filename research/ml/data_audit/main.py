"""CLI mỏng cho stage audit dữ liệu thô."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy audit và trả exit code."""

    parser = argparse.ArgumentParser(description="Kiểm tra raw data và quan hệ khóa.")
    parser.parse_args(argv)

    from .pipeline import run_data_audit

    run_data_audit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
