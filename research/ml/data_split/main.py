"""CLI mỏng cho leakage audit và data split."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy split pipeline và trả exit code."""

    parser = argparse.ArgumentParser(description="Audit leakage và tạo train/valid/test split.")
    parser.parse_args(argv)

    from .pipeline import run_data_split

    run_data_split()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
