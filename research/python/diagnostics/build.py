"""Build and write all Diagnostics & Mechanisms outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .claim_diagnostics import build_claim_base_frame
from .config import (
    CLAIM_DIAGNOSTICS_PATH,
    CLAIM_MECHANISM_SUMMARY_PATH,
    GENERATION_DIAGNOSTICS_PATH,
    GENERATION_MECHANISM_SUMMARY_PATH,
    OUTPUT_DIR,
    PIPELINE_FAILURES_PATH,
    SAFE_PHRASE_MATCHES_PATH,
)
from .generation_diagnostics import build_generation_diagnostics
from .safe_phrase import (
    extract_safe_phrase_items,
    match_claims_to_safe_phrases,
    match_generation_narratives,
)
from .summarize import (
    build_claim_mechanism_summary,
    build_generation_mechanism_summary,
    build_pipeline_failures,
)


def build_diagnostic_outputs(
    input_data: dict[str, Any],
    *,
    claim_type_count_columns: dict[str, str] | None = None,
    diagnostic_version: str | None = None,
    safe_phrase_enabled: bool = True,
) -> dict[str, pd.DataFrame]:
    """Run diagnostics in a short, explicit sequence.

    Optional parameters are opt-in. Historical callers retain exactly the
    original Home Credit behavior.
    """

    from .config import DIAGNOSTIC_VERSION

    version = diagnostic_version or DIAGNOSTIC_VERSION
    phrase_input = input_data
    if not safe_phrase_enabled:
        phrase_input = dict(input_data)
        phrase_input["evidence_items"] = input_data["evidence_items"].copy()
        phrase_input["evidence_items"]["safe_phrase"] = pd.NA
        phrase_input["evidence_packages"] = input_data["evidence_packages"].copy()
        phrase_input["evidence_packages"]["safe_phrase_count"] = 0

    claim_base = build_claim_base_frame(
        phrase_input,
        diagnostic_version=version,
    )
    safe_phrases = extract_safe_phrase_items(phrase_input)

    claim_diagnostics, safe_phrase_matches = (
        match_claims_to_safe_phrases(claim_base, safe_phrases)
    )

    narrative_matches = match_generation_narratives(
        input_data["generations"],
        safe_phrases,
    )
    generation_input = input_data if safe_phrase_enabled else phrase_input
    generation_diagnostics = build_generation_diagnostics(
        generation_input,
        claim_diagnostics,
        narrative_matches,
        claim_type_count_columns=claim_type_count_columns,
        diagnostic_version=version,
    )

    return {
        "claim_diagnostics": claim_diagnostics,
        "generation_diagnostics": generation_diagnostics,
        "claim_mechanism_summary": build_claim_mechanism_summary(
            claim_diagnostics
        ),
        "generation_mechanism_summary": (
            build_generation_mechanism_summary(
                generation_diagnostics
            )
        ),
        "safe_phrase_matches": safe_phrase_matches,
        "pipeline_failures": build_pipeline_failures(input_data),
    }


def write_diagnostic_outputs(
    outputs: dict[str, pd.DataFrame],
    output_dir: Path | None = None,
) -> None:
    """Write six deterministic CSV outputs."""

    target = output_dir or OUTPUT_DIR
    target.mkdir(parents=True, exist_ok=True)
    paths = {
        "claim_diagnostics": target / "claim_diagnostics.csv",
        "generation_diagnostics": target / "generation_diagnostics.csv",
        "claim_mechanism_summary": target / "claim_mechanism_summary.csv",
        "generation_mechanism_summary": target / "generation_mechanism_summary.csv",
        "safe_phrase_matches": target / "safe_phrase_matches.csv",
        "pipeline_failures": target / "pipeline_failures.csv",
    }

    for name, path in paths.items():
        outputs[name].to_csv(path, index=False, lineterminator="\n")


def output_paths(output_dir: Path | None = None) -> list[Path]:
    """Return generated CSV paths for tests and terminal checks."""

    if output_dir is None:
        return [
            CLAIM_DIAGNOSTICS_PATH,
            GENERATION_DIAGNOSTICS_PATH,
            CLAIM_MECHANISM_SUMMARY_PATH,
            GENERATION_MECHANISM_SUMMARY_PATH,
            SAFE_PHRASE_MATCHES_PATH,
            PIPELINE_FAILURES_PATH,
        ]
    return [
        output_dir / "claim_diagnostics.csv",
        output_dir / "generation_diagnostics.csv",
        output_dir / "claim_mechanism_summary.csv",
        output_dir / "generation_mechanism_summary.csv",
        output_dir / "safe_phrase_matches.csv",
        output_dir / "pipeline_failures.csv",
    ]
