from pathlib import Path

import pytest

from research.python.researchops.artifacts.exceptions import ArtifactValidationError
from research.python.researchops.artifacts.models import ArtifactProducer, ArtifactSource
from research.python.researchops.artifacts.package_builder import ArtifactPackageBuilder


def test_builder_records_counts_and_hashes(sample_package):
    manifest = sample_package.manifest
    csv_file = next(item for item in manifest.files if item.relative_path.endswith("data.csv"))
    assert csv_file.row_count == 1
    assert csv_file.column_count == 2
    assert csv_file.size_bytes > 0
    assert len(csv_file.sha256) == 64


def test_builder_rejects_duplicate_relative_path(tmp_path: Path, registry_sha: str):
    path = tmp_path / "a.txt"
    path.write_text("a", encoding="utf-8")
    builder = ArtifactPackageBuilder(
        artifact_type="release_metadata",
        schema_version="release_metadata_v1",
        producer=ArtifactProducer(
            stage_id="release.thesis_report",
            stage_version=1,
            stage_run_id=None,
            registry_sha256=registry_sha,
        ),
        source=ArtifactSource(source_commit="375cfa9"),
    )
    builder.add_file(path, relative_path="a.txt")
    with pytest.raises(ArtifactValidationError, match="Duplicate"):
        builder.add_file(path, relative_path="a.txt")
