"""CLI mỏng cho feature engineering."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy pipeline và trả exit code."""

    parser = argparse.ArgumentParser(description="Xây các customer-level feature group.")
    parser.parse_args(argv)

    from .pipeline import run_feature_engineering

    run_feature_engineering()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
