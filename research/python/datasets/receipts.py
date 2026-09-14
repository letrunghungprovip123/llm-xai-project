"""Deterministic stage receipts for dataset-scoped scientific boundaries.

Receipts are evidence, not mutable state flags.  A downstream stage should
validate the receipt and the referenced output hashes instead of trusting a
hand-edited ``Mxx=PASS`` ledger.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .profile import canonical_json_bytes


RECEIPT_SCHEMA_VERSION = "stage_receipt_v1"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


@dataclass(frozen=True)
class StageReceipt:
    stage: str
    stage_version: str
    dataset_id: str
    patch_id: str
    input_fingerprints: Mapping[str, str]
    config_fingerprints: Mapping[str, str]
    output_fingerprints: Mapping[str, str]
    invariants: Mapping[str, str]
    status: str = "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "stage": self.stage,
            "stage_version": self.stage_version,
            "dataset_id": self.dataset_id,
            "patch_id": self.patch_id,
            "input_fingerprints": dict(sorted(self.input_fingerprints.items())),
            "config_fingerprints": dict(sorted(self.config_fingerprints.items())),
            "output_fingerprints": dict(sorted(self.output_fingerprints.items())),
            "invariants": dict(sorted(self.invariants.items())),
            "status": self.status,
        }

    @property
    def receipt_fingerprint(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StageReceipt":
        if payload.get("schema_version") != RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported stage receipt schema_version")
        receipt = cls(
            stage=str(payload["stage"]),
            stage_version=str(payload["stage_version"]),
            dataset_id=str(payload["dataset_id"]),
            patch_id=str(payload["patch_id"]),
            input_fingerprints=dict(payload.get("input_fingerprints", {})),
            config_fingerprints=dict(payload.get("config_fingerprints", {})),
            output_fingerprints=dict(payload.get("output_fingerprints", {})),
            invariants=dict(payload.get("invariants", {})),
            status=str(payload.get("status", "")),
        )
        for group_name, group in (
            ("input_fingerprints", receipt.input_fingerprints),
            ("config_fingerprints", receipt.config_fingerprints),
            ("output_fingerprints", receipt.output_fingerprints),
        ):
            for key, digest in group.items():
                if len(str(digest)) != 64 or any(c not in "0123456789abcdef" for c in str(digest).lower()):
                    raise ValueError(f"{group_name}.{key} is not a SHA-256 digest")
        return receipt


def load_receipt(path: Path) -> StageReceipt:
    return StageReceipt.from_dict(json.loads(path.read_text(encoding="utf-8")))
