"""CLI mỏng cho feature matrix và registry."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy pipeline và trả exit code."""

    parser = argparse.ArgumentParser(description="Xây feature matrix và registry.")
    parser.parse_args(argv)

    from .pipeline import run_feature_matrix

    run_feature_matrix()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
