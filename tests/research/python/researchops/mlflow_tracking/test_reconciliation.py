from pathlib import Path

from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore
from research.python.researchops.mlflow_tracking.contracts import load_registry_policy
from research.python.researchops.mlflow_tracking.receipts import build_receipt, build_receipt_package
from research.python.researchops.mlflow_tracking.reconciliation import reconcile_mlflow
from research.python.researchops.mlflow_tracking.registry import register_training_models
from tests.research.python.researchops.mlflow_tracking.test_registry import FakeRegistryGateway, tracking_result


def _setup(tmp_path, package):
    store = FilesystemArtifactStore(tmp_path / "store")
    store.put_package(package)
    gateway = FakeRegistryGateway()
    tracking = tracking_result(package)
    for item in tracking.models:
        gateway.runs[item.run_id] = __import__("research.python.researchops.mlflow_tracking.models", fromlist=["RunSnapshot"]).RunSnapshot(item.run_id, "FINISHED", {})
    registration = register_training_models(
        tracking=tracking,
        source_manifest=package.manifest,
        gateway=gateway,
        policy=load_registry_policy(),
    )
    receipt = build_receipt(tracking=tracking, registration=registration, mlflow_version="3.14.0")
    built, temporary = build_receipt_package(store=store, source_artifact_id=package.manifest.artifact_id, receipt=receipt)
    try:
        store.put_package(built)
    finally:
        temporary.cleanup()
    return store, gateway


def test_reconciliation_passes_and_detects_candidate_alias_drift(tmp_path: Path, training_release_package):
    store, gateway = _setup(tmp_path, training_release_package)
    report = reconcile_mlflow(store=store, gateway=gateway, policy=load_registry_policy())
    assert report.passed is True
    gateway.set_alias("credit-risk-predictor", "candidate", "1")
    drift = reconcile_mlflow(store=store, gateway=gateway, policy=load_registry_policy())
    assert drift.passed is False
    assert drift.alias_drift


def test_reconciliation_uses_latest_receipt_and_ignores_superseded_source_uri_versions(
    tmp_path: Path,
    training_release_package,
):
    store, gateway = _setup(tmp_path, training_release_package)
    tracking = tracking_result(training_release_package)

    for index, version in enumerate(list(gateway.versions)):
        gateway.versions[index] = type(version)(
            version.name,
            version.version,
            version.run_id,
            version.source,
            version.status,
            {
                **version.tags,
                "researchops.registry_record_status": "SUPERSEDED_SOURCE_URI",
            },
        )

    corrected_gateway = gateway
    corrected_tracking = type(tracking)(
        source_artifact_id=tracking.source_artifact_id,
        source_manifest_sha256=tracking.source_manifest_sha256,
        experiment_id=tracking.experiment_id,
        parent_run_id=tracking.parent_run_id,
        parent_reused=True,
        models=tuple(
            type(item)(
                model_name=item.model_name,
                run_id=item.run_id,
                model_uri=item.model_uri.replace("models:/m-", "models:/m-corrected-"),
                tracking_key=item.tracking_key,
                selected_as_best=item.selected_as_best,
                reused=True,
            )
            for item in tracking.models
        ),
    )
    corrected_registration = register_training_models(
        tracking=corrected_tracking,
        source_manifest=training_release_package.manifest,
        gateway=corrected_gateway,
        policy=load_registry_policy(),
    )
    corrected_receipt = build_receipt(
        tracking=corrected_tracking,
        registration=corrected_registration,
        mlflow_version="3.14.0",
    )
    built, temporary = build_receipt_package(
        store=store,
        source_artifact_id=training_release_package.manifest.artifact_id,
        receipt=corrected_receipt,
    )
    try:
        store.put_package(built)
    finally:
        temporary.cleanup()

    report = reconcile_mlflow(
        store=store,
        gateway=corrected_gateway,
        policy=load_registry_policy(),
    )

    assert report.passed is True
    assert report.orphan_model_versions == ()
    assert len(report.receipt_artifact_ids) == 2
