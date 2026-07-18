"""CLI mỏng cho preprocessing."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy preprocessing và trả exit code."""

    parser = argparse.ArgumentParser(description="Fit preprocessing trên train và transform valid/test.")
    parser.parse_args(argv)

    from .pipeline import run_preprocessing

    run_preprocessing()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
