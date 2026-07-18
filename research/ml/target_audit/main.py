"""CLI mỏng cho stage audit TARGET, missing values và anomaly."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy audit và trả exit code."""

    parser = argparse.ArgumentParser(description="Kiểm tra target, missing và anomaly.")
    parser.parse_args(argv)

    from .pipeline import run_target_audit

    run_target_audit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
