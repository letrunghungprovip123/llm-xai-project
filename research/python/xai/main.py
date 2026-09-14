"""CLI mỏng cho SHAP/XAI."""

from __future__ import annotations

import argparse
import traceback

from .config import DEFAULT_RUN_MODE, SUPPORTED_RUN_MODES


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy XAI pipeline và trả exit code."""

    parser = argparse.ArgumentParser(description="Chạy Batch G — XAI Evidence Layer.")
    parser.add_argument("--mode", choices=SUPPORTED_RUN_MODES, default=DEFAULT_RUN_MODE)
    args = parser.parse_args(argv)

    from .pipeline import print_section, run_pipeline

    try:
        result = run_pipeline(run_mode=args.mode)
        return 1 if result.status == "FAILED" else 0
    except Exception as exc:
        print_section("Batch G failed")
        print("Error type:", type(exc).__name__)
        print("Error message:", exc)
        print("\nTraceback:")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
