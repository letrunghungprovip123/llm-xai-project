from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.python.researchops.orchestration import stage_commands


def test_verify_environment_writes_machine_report(tmp_path: Path, monkeypatch):
    run_dir = Path.cwd() / ".researchops" / "test-stage-commands"
    monkeypatch.setenv("RESEARCHOPS_RUN_DIR", str(run_dir))
    try:
        report = stage_commands.verify_environment()
        assert report["passed"] is True
        saved = json.loads(
            (run_dir / "environment_verification_report.json").read_text()
        )
        assert saved == report
    finally:
        import shutil
        shutil.rmtree(run_dir, ignore_errors=True)


def test_acceptance_fixture_transient_once_is_deterministic(tmp_path: Path, monkeypatch):
    root = Path.cwd() / ".researchops" / "test-transient-fixture"
    run_dir = root / "stage" / "attempt"
    monkeypatch.setenv("RESEARCHOPS_RUN_DIR", str(run_dir))
    monkeypatch.setenv("RESEARCHOPS_PIPELINE_RUN_ID", "pipeline-test")
    monkeypatch.setenv("RESEARCHOPS_STAGE_RUN_ID", "stage-test")
    monkeypatch.setenv("RESEARCHOPS_PARAMETER_SIMULATION", '"transient-once"')
    try:
        with pytest.raises(SystemExit) as raised:
            stage_commands.acceptance_fixture()
        assert raised.value.code == 75
        report = stage_commands.acceptance_fixture()
        assert report["output_written"] is True
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)


def test_mlflow_register_adapts_typed_input_to_canonical_receipt(
    monkeypatch,
):
    import sys
    from types import ModuleType

    root = Path.cwd() / ".researchops" / "test-mlflow-stage-command"
    run_dir = root / "pipeline" / "stage"
    report_path = run_dir / "stage-report.json"
    source_id = "artifact_trained_model_01J00000000000000000000000"
    source_sha = "a" * 64
    receipt_id = "artifact_mlflow_registration_receipt_01J00000000000000000000000"
    receipt_sha = "b" * 64

    fake_cli = ModuleType("research.python.researchops.mlflow_tracking.cli")

    def fake_main(argv):
        assert argv[:5] == [
            "register-training-release",
            "--artifact-profile",
            "development-minio",
            "--artifact-id",
            source_id,
        ]
        target = Path(argv[argv.index("--report-path") + 1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "schema_version": "mlflow_training_registration_result_v1",
                    "receipt_artifact_id": receipt_id,
                    "receipt_manifest_sha256": receipt_sha,
                    "receipt_reused": True,
                    "tracking": {
                        "source_artifact_id": source_id,
                        "source_manifest_sha256": source_sha,
                        "parent_run_id": "parent-run",
                    },
                    "registry": {
                        "source_artifact_id": source_id,
                        "source_manifest_sha256": source_sha,
                        "candidate_version": "9",
                        "registered_model_name": "credit-risk-predictor",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return 0

    fake_cli.main = fake_main
    monkeypatch.setitem(
        sys.modules,
        "research.python.researchops.mlflow_tracking.cli",
        fake_cli,
    )
    monkeypatch.setenv("RESEARCHOPS_RUN_DIR", str(run_dir))
    monkeypatch.setenv("RESEARCHOPS_REPORT_PATH", str(report_path))
    monkeypatch.setenv(
        "RESEARCHOPS_INPUT_TRAINED_MODELS_ARTIFACT_ID", source_id
    )
    monkeypatch.setenv(
        "RESEARCHOPS_INPUT_TRAINED_MODELS_MANIFEST_SHA256", source_sha
    )
    monkeypatch.setenv(
        "RESEARCHOPS_INPUT_TRAINED_MODELS_CONTRACT", "trained_model"
    )
    try:
        report = stage_commands.mlflow_register()
        assert report["schema_version"] == "stage_command_result_v1"
        assert report["outputs"]["receipt"] == {
            "artifact_id": receipt_id,
            "artifact_type": "mlflow_registration_receipt",
            "manifest_sha256": receipt_sha,
            "source_inputs": ["trained_models"],
        }
        assert json.loads(report_path.read_text(encoding="utf-8")) == report
    finally:
        import shutil

        shutil.rmtree(root, ignore_errors=True)


def test_mlflow_register_rejects_source_identity_drift(monkeypatch):
    payload = {
        "schema_version": "mlflow_training_registration_result_v1",
        "receipt_artifact_id": (
            "artifact_mlflow_registration_receipt_01J00000000000000000000000"
        ),
        "receipt_manifest_sha256": "b" * 64,
        "tracking": {
            "source_artifact_id": "artifact_trained_model_wrong",
            "source_manifest_sha256": "a" * 64,
        },
        "registry": {
            "source_artifact_id": "artifact_trained_model_wrong",
            "source_manifest_sha256": "a" * 64,
        },
    }
    with pytest.raises(RuntimeError, match="does not match the stage input"):
        stage_commands._require_registration_result(
            payload,
            source_artifact_id=(
                "artifact_trained_model_01J00000000000000000000000"
            ),
            source_manifest_sha256="a" * 64,
        )
