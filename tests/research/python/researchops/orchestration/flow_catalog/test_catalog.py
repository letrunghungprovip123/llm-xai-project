from __future__ import annotations

from copy import deepcopy

from research.python.researchops.orchestration.flow_catalog.loader import (
    load_flow_catalog,
)
from research.python.researchops.orchestration.flow_catalog.models import FlowCatalog
from research.python.researchops.orchestration.flow_catalog.validator import (
    validate_flow_catalog,
)


def _payload() -> dict:
    return deepcopy(load_flow_catalog().model_dump(mode="json"))


def _flow(payload: dict, flow_id: str) -> dict:
    return next(item for item in payload["flows"] if item["id"] == flow_id)


def test_real_catalog_is_valid_and_covers_all_stages():
    report = validate_flow_catalog(load_flow_catalog())

    assert report.passed
    assert report.flow_count == 15
    assert report.covered_stage_count == report.stage_count == 42
    assert report.missing_stage_ids == ()
    assert report.unknown_stage_ids == ()


def test_unknown_stage_fails_closed():
    payload = _payload()
    _flow(payload, "train_model_release")["nodes"][0]["stage_id"] = "ops.unknown"

    report = validate_flow_catalog(FlowCatalog.model_validate(payload))

    assert not report.passed
    assert "ops.unknown" in report.unknown_stage_ids
    assert any("unknown stage" in error for error in report.errors)


def test_stage_input_contract_mismatch_fails_closed():
    payload = _payload()
    _flow(payload, "train_model_release")["inputs"][0]["contract"] = (
        "canonical_generations"
    )

    report = validate_flow_catalog(FlowCatalog.model_validate(payload))

    assert not report.passed
    assert any("contract mismatch" in error for error in report.errors)


def test_provider_flow_requires_exact_approval_policy_set():
    payload = _payload()
    _flow(payload, "generate_llm_batch")["approval_policies"] = []

    report = validate_flow_catalog(FlowCatalog.model_validate(payload))

    assert not report.passed
    assert any("approval policy mismatch" in error for error in report.errors)


def test_stage_queue_mapping_is_enforced():
    payload = _payload()
    flow = _flow(payload, "generate_llm_batch")
    flow["nodes"][0]["work_queue"] = "verification"

    report = validate_flow_catalog(FlowCatalog.model_validate(payload))

    assert not report.passed
    assert any("does not match stage policy" in error for error in report.errors)


def test_optional_registry_stage_cannot_be_required():
    payload = _payload()
    flow = _flow(payload, "register_verified_training_release")
    flow["nodes"][0]["required"] = True
    flow["nodes"][0].pop("condition")

    report = validate_flow_catalog(FlowCatalog.model_validate(payload))

    assert not report.passed
    assert any("OPTIONAL stage must be an optional node" in error for error in report.errors)


def test_stale_stage_registry_hash_fails_closed():
    payload = _payload()
    payload["stage_registry_sha256"] = "0" * 64

    report = validate_flow_catalog(FlowCatalog.model_validate(payload))

    assert not report.passed
    assert any("stage_registry_sha256 is stale" in error for error in report.errors)


def test_missing_stage_coverage_fails_closed():
    payload = _payload()
    payload["flows"] = [
        item
        for item in payload["flows"]
        if item["id"] != "certify_dashboard_release"
    ]

    report = validate_flow_catalog(FlowCatalog.model_validate(payload))

    assert not report.passed
    assert report.missing_stage_ids == ("dashboard.i18n_certification",)
