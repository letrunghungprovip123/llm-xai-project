"""Đọc và xác minh claim-measurement release dùng cho báo cáo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.python.common.hashing import sha256_file
from research.python.common.paths import DEFAULT_PATHS


RELEASE_PATH = (
    DEFAULT_PATHS.project_root
    / "config"
    / "research"
    / "claim_measurement_release_v1.json"
)
ALLOWED_RELEASE_STATUSES = {"READY", "READY_WITH_LIMITATIONS"}


def load_claim_measurement_release(
    release_path: Path = RELEASE_PATH,
) -> dict[str, Any]:
    """Load the single report-facing claim release and validate its shape."""

    if not release_path.is_file():
        raise FileNotFoundError(
            f"Claim measurement release is missing: {release_path}"
        )

    release = json.loads(release_path.read_text(encoding="utf-8"))
    if not isinstance(release, dict):
        raise ValueError("Claim measurement release must be a JSON object.")

    status = release.get("release_status")
    if status not in ALLOWED_RELEASE_STATUSES:
        raise ValueError(
            "Claim measurement release is not approved for reporting: "
            f"{status!r}"
        )

    official = release.get("official")
    artifacts = official.get("artifacts") if isinstance(official, dict) else None
    required_artifacts = {
        "final_claims",
        "validation_results",
        "generation_summaries",
    }
    if not isinstance(artifacts, dict) or not required_artifacts.issubset(artifacts):
        raise ValueError("Official release artifact contract is incomplete.")

    return release


def resolve_official_release_paths(
    release: dict[str, Any],
) -> dict[str, Path]:
    """Resolve official artifact paths relative to the repository root."""

    project_root = DEFAULT_PATHS.project_root
    artifacts = release["official"]["artifacts"]
    return {
        name: project_root / str(contract["path"])
        for name, contract in artifacts.items()
    }


def verify_official_release_artifacts(
    release: dict[str, Any],
) -> dict[str, Path]:
    """Fail closed when an approved artifact is missing or hash-mismatched."""

    resolved = resolve_official_release_paths(release)
    artifacts = release["official"]["artifacts"]

    for name, path in resolved.items():
        if not path.is_file():
            raise FileNotFoundError(
                f"Approved release artifact does not exist ({name}): {path}"
            )

        expected_hash = str(artifacts[name]["sha256"])
        observed_hash = sha256_file(path)
        if observed_hash != expected_hash:
            raise ValueError(
                "Approved release artifact hash mismatch for "
                f"{name}: expected {expected_hash}, observed {observed_hash}"
            )

    return resolved


def verify_manifest_artifacts(
    artifacts: list[dict[str, Any]],
    *,
    contract_name: str,
    project_root: Path | None = None,
) -> list[Path]:
    """Verify project-relative manifest artifacts and fail closed.

    Each artifact must provide ``path`` and ``sha256``. When ``byte_count``
    is present it is verified as well. The function returns the resolved
    paths only after every contract has passed.
    """

    root = project_root or DEFAULT_PATHS.project_root
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError(f"{contract_name} has no artifact contracts.")

    resolved: list[Path] = []
    for index, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            raise ValueError(
                f"{contract_name} artifact #{index} must be an object."
            )
        relative_path = artifact.get("path")
        expected_hash = artifact.get("sha256")
        if not relative_path or not expected_hash:
            raise ValueError(
                f"{contract_name} artifact #{index} is missing path/hash."
            )
        path = root / str(relative_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"{contract_name} artifact does not exist: {path}"
            )
        observed_hash = sha256_file(path)
        if observed_hash != str(expected_hash):
            raise ValueError(
                f"{contract_name} hash mismatch for {relative_path}: "
                f"expected {expected_hash}, observed {observed_hash}"
            )
        expected_bytes = artifact.get("byte_count")
        if expected_bytes is not None and path.stat().st_size != int(expected_bytes):
            raise ValueError(
                f"{contract_name} byte-count mismatch for {relative_path}: "
                f"expected {expected_bytes}, observed {path.stat().st_size}"
            )
        resolved.append(path)
    return resolved


def verify_report_release_manifest(
    manifest: dict[str, Any],
) -> list[Path]:
    """Verify every certified artifact in a thesis report manifest."""

    return verify_manifest_artifacts(
        manifest.get("certified_report_files", []),
        contract_name="Certified report release",
    )
