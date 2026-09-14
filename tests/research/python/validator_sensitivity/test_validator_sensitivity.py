"""Tests for Candidate-versus-V4 generation-level sensitivity."""

from research.python.validator_sensitivity.build import (
    build_outputs,
    read_jsonl,
)
from research.python.validator_sensitivity.config import (
    CANDIDATE_SUMMARY_PATH,
    V4_SUMMARY_PATH,
)


def test_validator_sensitivity_keeps_all_generations_and_cases() -> None:
    outputs = build_outputs(
        read_jsonl(CANDIDATE_SUMMARY_PATH),
        read_jsonl(V4_SUMMARY_PATH),
    )
    pairs = outputs["pairs"]
    tests = outputs["tests"]

    assert len(pairs) == 648
    assert pairs["generation_id"].nunique() == 648
    assert pairs["case_id"].nunique() == 36
    assert set(tests["paired_case_count"]) == {36}
    assert set(tests["analysis_role"]) == {"VALIDATOR_SENSITIVITY"}
