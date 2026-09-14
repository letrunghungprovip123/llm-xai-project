"""CLI mỏng cho model training và evaluation."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy model pipeline và trả exit code."""

    parser = argparse.ArgumentParser(description="Train, evaluate và chọn model tốt nhất.")
    parser.parse_args(argv)

    from .pipeline import print_section, run_model_training_layer

    try:
        run_model_training_layer()
    except Exception as exc:
        print_section("Batch F Failed")
        print("Status: FAILED")
        print(f"Error type: {type(exc).__name__}")
        print(f"Error message: {exc}")
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
