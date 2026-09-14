from __future__ import annotations

from research.python.researchops.control_plane.openapi import schema_payload


def test_openapi_exposes_controlled_mutations_without_generic_gate_write():
    schema = schema_payload()
    paths = schema["paths"]
    assert "post" in paths["/api/v1/runs"]
    assert "post" in paths["/api/v1/artifacts/{artifact_id}/evaluations"]
    assert "post" in paths["/api/v1/releases/{release_id}/promotions"]
    assert "post" in paths[
        "/api/v1/models/{model_name}/versions/{version}/promotions"
    ]
    assert "/api/v1/gates/evaluate" not in paths
    assert not (
        "/api/v1/releases" in paths and "post" in paths["/api/v1/releases"]
    )


def test_mutation_operations_require_idempotency_header():
    schema = schema_payload()
    operation = schema["paths"]["/api/v1/runs"]["post"]
    parameters = operation.get("parameters", [])
    assert any(
        item.get("in") == "header"
        and item.get("name") == "Idempotency-Key"
        and item.get("required") is True
        for item in parameters
    )
