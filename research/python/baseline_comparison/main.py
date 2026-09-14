"""CLI for the deterministic Template Baseline analytical layer."""

from __future__ import annotations

import json

from .build import build_manifest, build_outputs, write_outputs
from .config import (
    CASES_PATH,
    CLAIM_RELEASE_PATH,
    EVIDENCE_ITEMS_PATH,
    EVIDENCE_LEVELS_PATH,
    EVIDENCE_PACKAGES_PATH,
    LLM_GENERATIONS_PATH,
    LLM_GENERATION_METRICS_PATH,
    MANIFEST_PATH,
    MODELS_PATH,
    OUTPUT_PATHS,
    REPORT_MANIFEST_PATH,
    REPORT_READINESS_PATH,
    RQ_CONTRACT_PATH,
    TEMPLATE_INDEX_PATH,
    VALIDATION_PATH,
)
from .load import load_baseline_inputs
from .validate import validate_outputs


def main() -> int:
    input_data = load_baseline_inputs()
    outputs = build_outputs(input_data)
    validation = validate_outputs(outputs, input_data)
    write_outputs(outputs)
    manifest = build_manifest(
        input_paths=[
            TEMPLATE_INDEX_PATH,
            CASES_PATH,
            EVIDENCE_PACKAGES_PATH,
            EVIDENCE_ITEMS_PATH,
            LLM_GENERATIONS_PATH,
            LLM_GENERATION_METRICS_PATH,
            MODELS_PATH,
            EVIDENCE_LEVELS_PATH,
            REPORT_MANIFEST_PATH,
    REPORT_READINESS_PATH,
            CLAIM_RELEASE_PATH,
            RQ_CONTRACT_PATH,
        ],
        output_paths=list(OUTPUT_PATHS.values()),
        parent_release=input_data["report_readiness"],
        claim_release=input_data["claim_release"],
    )
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    VALIDATION_PATH.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("Template Baseline comparison")
    print(f"- Baseline generations: {len(outputs['baseline_generation_metrics'])}")
    print(f"- LLM-template pairs: {len(outputs['llm_vs_template_case_pairs'])}")
    print(f"- Case-level tests: {len(outputs['llm_vs_template_tests'])}")
    print(f"- Exit gate: {validation['exit_gate']}")
    return 0 if validation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
