"""CLI mỏng cho evidence exposure S0–S5."""

from __future__ import annotations

import argparse

from .config import DEFAULT_RUN_MODE, MANIFEST_DIR


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, chạy evidence builder và trả exit code."""

    parser = argparse.ArgumentParser(description="Xây evidence packages S0–S5.")
    parser.add_argument(
        "--run-mode",
        choices=("development", "evaluation"),
        default=DEFAULT_RUN_MODE,
    )
    parser.add_argument("--input", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--manifest-dir", default=str(MANIFEST_DIR))
    parser.add_argument("--disallow-overlap-with", default=None)
    args = parser.parse_args(argv)

    from .pipeline import run_evidence_exposure

    quality_report = run_evidence_exposure(
        run_mode=args.run_mode,
        input_path=args.input,
        output_dir=args.output_dir,
        manifest_dir=args.manifest_dir,
        disallow_overlap_with=args.disallow_overlap_with,
    )
    return 1 if quality_report.get("status") == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
