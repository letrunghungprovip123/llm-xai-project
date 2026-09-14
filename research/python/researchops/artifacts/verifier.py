from __future__ import annotations

from pathlib import Path

from .exceptions import ArtifactIntegrityError
from .hashing import sha256_file
from .manifest import load_manifest
from .models import ArtifactVerificationResult
from .paths import safe_join


def verify_package_directory(package_directory: Path) -> ArtifactVerificationResult:
    manifest_path = package_directory / "manifest.json"
    manifest = load_manifest(manifest_path)
    errors: list[str] = []
    for item in manifest.files:
        path = safe_join(package_directory / "files", item.relative_path)
        if not path.is_file():
            errors.append(f"Missing file: {item.relative_path}")
            continue
        observed_size = path.stat().st_size
        if observed_size != item.size_bytes:
            errors.append(
                f"Size mismatch for {item.relative_path}: "
                f"expected={item.size_bytes} observed={observed_size}"
            )
            continue
        observed_sha = sha256_file(path)
        if observed_sha != item.sha256:
            errors.append(
                f"SHA-256 mismatch for {item.relative_path}: "
                f"expected={item.sha256} observed={observed_sha}"
            )
    return ArtifactVerificationResult(
        artifact_id=manifest.artifact_id,
        manifest_sha256=manifest.manifest_sha256,
        passed=not errors,
        checked_files=len(manifest.files),
        errors=tuple(errors),
    )


def require_verified_package(package_directory: Path) -> ArtifactVerificationResult:
    result = verify_package_directory(package_directory)
    if not result.passed:
        raise ArtifactIntegrityError("; ".join(result.errors))
    return result
