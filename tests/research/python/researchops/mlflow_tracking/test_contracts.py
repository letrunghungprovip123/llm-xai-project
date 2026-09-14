from research.python.researchops.mlflow_tracking.contracts import (
    load_experiment_catalog,
    load_registry_policy,
    load_tracking_contract,
    validate_contract_set,
)


def test_contract_set_is_consistent():
    result = validate_contract_set()
    assert result["passed"] is True
    assert result["experiment_count"] == 6
    assert result["mlflow_version"] == "3.14.0"


def test_registry_policy_blocks_training_champion_assignment():
    policy = load_registry_policy()
    assert policy.training_code_may_assign_champion is False
    assert set(policy.aliases) == {"candidate", "champion", "archived-reference"}


def test_tracking_contract_uses_parent_child_runs():
    contract = load_tracking_contract()
    assert contract.run_structure == "parent_with_model_children"
    assert "researchops.tracking_key" in contract.required_run_tags
    assert load_experiment_catalog().experiments[0].name == "credit-risk-modeling"


def test_receipt_schema_is_present_and_governance_catalogs_include_mlflow():
    import json
    from pathlib import Path

    schema = json.loads(Path("config/platform/schemas/mlflow_registration_receipt_v1.schema.json").read_text())
    artifacts = json.loads(Path("config/platform/artifact_types_v1.json").read_text())
    gates = json.loads(Path("config/platform/gate_catalog_v1.json").read_text())
    assert schema["$id"] == "mlflow_registration_receipt_v1"
    assert "mlflow_registration_receipt" in {item["artifact_type"] for item in artifacts["artifact_types"]}
    assert "MLFLOW_MODEL_REGISTERED" in {item["gate_id"] for item in gates["gates"]}
