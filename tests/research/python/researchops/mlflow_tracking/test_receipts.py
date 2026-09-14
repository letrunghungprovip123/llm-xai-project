from pathlib import Path

from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore
from research.python.researchops.mlflow_tracking.contracts import load_registry_policy
from research.python.researchops.mlflow_tracking.receipts import (
    build_receipt,
    build_receipt_package,
    find_receipts_for_source,
    load_receipt,
    publish_receipt,
)
from research.python.researchops.mlflow_tracking.registry import register_training_models
from tests.research.python.researchops.mlflow_tracking.test_registry import FakeRegistryGateway, tracking_result


def test_receipt_package_is_immutable_child_of_training_artifact(tmp_path: Path, training_release_package):
    store = FilesystemArtifactStore(tmp_path / "store")
    store.put_package(training_release_package)
    tracking = tracking_result(training_release_package)
    gateway = FakeRegistryGateway()
    registration = register_training_models(
        tracking=tracking,
        source_manifest=training_release_package.manifest,
        gateway=gateway,
        policy=load_registry_policy(),
    )
    receipt = build_receipt(tracking=tracking, registration=registration, mlflow_version="3.14.0")
    package, temporary = build_receipt_package(
        store=store,
        source_artifact_id=training_release_package.manifest.artifact_id,
        receipt=receipt,
    )
    try:
        reference = store.put_package(package)
    finally:
        temporary.cleanup()
    manifest = store.get_manifest(reference.artifact_id)
    assert manifest.artifact_type == "mlflow_registration_receipt"
    assert manifest.producer.stage_id == "ops.mlflow_register"
    assert manifest.parents[0].artifact_id == training_release_package.manifest.artifact_id
    assert manifest.parents[0].relationship == "registered_in_mlflow"
    loaded = load_receipt(store, reference.artifact_id, tmp_path / "download")
    assert loaded.candidate_version == "3"
    assert loaded.registered_model_name == "credit-risk-predictor"


def test_publish_receipt_is_idempotent_and_schema_valid(tmp_path: Path, training_release_package):
    import json
    import jsonschema

    store = FilesystemArtifactStore(tmp_path / "store")
    store.put_package(training_release_package)
    tracking = tracking_result(training_release_package)
    gateway = FakeRegistryGateway()
    registration = register_training_models(
        tracking=tracking,
        source_manifest=training_release_package.manifest,
        gateway=gateway,
        policy=load_registry_policy(),
    )
    receipt = build_receipt(
        tracking=tracking, registration=registration, mlflow_version="3.14.0"
    )
    first, first_reused = publish_receipt(
        store=store,
        source_artifact_id=training_release_package.manifest.artifact_id,
        receipt=receipt,
    )
    second, second_reused = publish_receipt(
        store=store,
        source_artifact_id=training_release_package.manifest.artifact_id,
        receipt=receipt,
    )
    assert first == second
    assert first_reused is False
    assert second_reused is True
    receipts = [
        item for item in store.list_artifact_ids()
        if store.get_manifest(item).artifact_type == "mlflow_registration_receipt"
    ]
    assert len(receipts) == 1
    payload = load_receipt(store, first.artifact_id, tmp_path / "schema-download").model_dump(mode="json")
    schema = json.loads(
        Path("config/platform/schemas/mlflow_registration_receipt_v1.schema.json").read_text()
    )
    jsonschema.validate(payload, schema)


def test_publish_receipt_allows_new_immutable_revision_for_corrected_registry_state(
    tmp_path: Path,
    training_release_package,
):
    store = FilesystemArtifactStore(tmp_path / "store")
    store.put_package(training_release_package)
    tracking = tracking_result(training_release_package)
    gateway = FakeRegistryGateway()
    first_registration = register_training_models(
        tracking=tracking,
        source_manifest=training_release_package.manifest,
        gateway=gateway,
        policy=load_registry_policy(),
    )
    first_receipt = build_receipt(
        tracking=tracking,
        registration=first_registration,
        mlflow_version="3.14.0",
    )
    first_ref, _ = publish_receipt(
        store=store,
        source_artifact_id=training_release_package.manifest.artifact_id,
        receipt=first_receipt,
    )

    # Build a corrected tracking result with the same source and tracking keys.
    from research.python.researchops.mlflow_tracking.models import (
        TrackedModelRun,
        TrainingTrackingResult,
    )
    corrected_tracking = TrainingTrackingResult(
        source_artifact_id=tracking.source_artifact_id,
        source_manifest_sha256=tracking.source_manifest_sha256,
        experiment_id=tracking.experiment_id,
        parent_run_id=tracking.parent_run_id,
        parent_reused=True,
        models=tuple(
            TrackedModelRun(
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
    second_gateway = FakeRegistryGateway()
    second_registration = register_training_models(
        tracking=corrected_tracking,
        source_manifest=training_release_package.manifest,
        gateway=second_gateway,
        policy=load_registry_policy(),
    )
    second_receipt = build_receipt(
        tracking=corrected_tracking,
        registration=second_registration,
        mlflow_version="3.14.0",
    )
    second_ref, second_reused = publish_receipt(
        store=store,
        source_artifact_id=training_release_package.manifest.artifact_id,
        receipt=second_receipt,
    )

    assert first_ref.artifact_id != second_ref.artifact_id
    assert second_reused is False
    assert len(find_receipts_for_source(store, tracking.source_artifact_id)) == 2
    reused_ref, reused = publish_receipt(
        store=store,
        source_artifact_id=training_release_package.manifest.artifact_id,
        receipt=second_receipt,
    )
    assert reused is True
    assert reused_ref.artifact_id == second_ref.artifact_id
