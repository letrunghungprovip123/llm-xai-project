from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from research.python.researchops.artifacts.stores.base import ArtifactStore

from .contracts import RegistryPolicy
from .receipts import MLflowRegistrationReceiptV1, load_receipt
from .registry_gateway import RegistryGateway


@dataclass(frozen=True)
class MLflowReconciliationReport:
    receipt_artifact_ids: tuple[str, ...]
    dangling_receipts: tuple[str, ...]
    orphan_model_versions: tuple[str, ...]
    alias_drift: tuple[str, ...]
    manifest_hash_mismatches: tuple[str, ...]
    duplicate_tracking_keys: tuple[str, ...]
    missing_runs: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not any((
            self.dangling_receipts,
            self.orphan_model_versions,
            self.alias_drift,
            self.manifest_hash_mismatches,
            self.duplicate_tracking_keys,
            self.missing_runs,
        ))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "mlflow_reconciliation_report_v1",
            "passed": self.passed,
            "receipt_artifact_ids": list(self.receipt_artifact_ids),
            "dangling_receipts": list(self.dangling_receipts),
            "orphan_model_versions": list(self.orphan_model_versions),
            "alias_drift": list(self.alias_drift),
            "manifest_hash_mismatches": list(self.manifest_hash_mismatches),
            "duplicate_tracking_keys": list(self.duplicate_tracking_keys),
            "missing_runs": list(self.missing_runs),
        }


def reconcile_mlflow(
    *,
    store: ArtifactStore,
    gateway: RegistryGateway,
    policy: RegistryPolicy,
) -> MLflowReconciliationReport:
    receipt_ids = tuple(sorted(
        artifact_id
        for artifact_id in store.list_artifact_ids()
        if store.get_manifest(artifact_id).artifact_type == "mlflow_registration_receipt"
    ))
    receipt_records: list[tuple[str, MLflowRegistrationReceiptV1]] = []
    with tempfile.TemporaryDirectory(prefix="researchops-mlflow-reconcile-") as directory:
        for index, artifact_id in enumerate(receipt_ids):
            receipt_records.append((
                artifact_id,
                load_receipt(store, artifact_id, Path(directory) / str(index)),
            ))

    latest_by_source: dict[str, tuple[str, MLflowRegistrationReceiptV1]] = {}
    for artifact_id, receipt in receipt_records:
        current = latest_by_source.get(receipt.source_model_artifact_id)
        if current is None or receipt.created_at > current[1].created_at:
            latest_by_source[receipt.source_model_artifact_id] = (artifact_id, receipt)
    receipts = [item[1] for item in latest_by_source.values()]

    dangling: list[str] = []
    alias_drift: list[str] = []
    hash_mismatches: list[str] = []
    missing_runs: list[str] = []
    receipt_version_keys: set[tuple[str, str]] = set()
    receipt_tracking_keys: list[str] = []

    latest_receipt = max(receipts, key=lambda item: item.created_at) if receipts else None
    if latest_receipt is not None:
        candidate = latest_receipt.candidate_version
        actual_candidate = gateway.alias_version(
            latest_receipt.registered_model_name, "candidate"
        )
        if actual_candidate != candidate:
            alias_drift.append(
                f"{latest_receipt.registered_model_name}:candidate "
                f"expected={candidate} actual={actual_candidate}"
            )

    for receipt in receipts:
        for item in receipt.versions:
            receipt_tracking_keys.append(item.tracking_key)
            receipt_version_keys.add((receipt.registered_model_name, item.version))
            version = gateway.get_version(receipt.registered_model_name, item.version)
            if version is None:
                dangling.append(f"{receipt.registered_model_name}:{item.version}")
                continue
            if version.tags.get("researchops.source_manifest_sha256") != receipt.source_model_manifest_sha256:
                hash_mismatches.append(f"{receipt.registered_model_name}:{item.version}")
            if gateway.get_run(item.run_id) is None:
                missing_runs.append(item.run_id)

    counts: dict[str, int] = {}
    for key in receipt_tracking_keys:
        counts[key] = counts.get(key, 0) + 1
    duplicate_keys = sorted(key for key, count in counts.items() if count > 1)

    orphan = sorted(
        f"{item.name}:{item.version}"
        for item in gateway.list_versions(policy.registered_model_name)
        if item.tags.get("researchops.project") == "llm-xai"
        and item.tags.get("researchops.registry_record_status")
        != "SUPERSEDED_SOURCE_URI"
        and (item.name, item.version) not in receipt_version_keys
    )
    return MLflowReconciliationReport(
        receipt_artifact_ids=receipt_ids,
        dangling_receipts=tuple(sorted(set(dangling))),
        orphan_model_versions=tuple(orphan),
        alias_drift=tuple(sorted(set(alias_drift))),
        manifest_hash_mismatches=tuple(sorted(set(hash_mismatches))),
        duplicate_tracking_keys=tuple(duplicate_keys),
        missing_runs=tuple(sorted(set(missing_runs))),
    )
