from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.python.researchops.artifacts.hashing import sha256_file
from research.python.researchops.artifacts.models import ArtifactProducer, ArtifactSource
from research.python.researchops.artifacts.package_builder import ArtifactPackageBuilder


@pytest.fixture
def registry_sha() -> str:
    payload = json.loads(
        Path("config/platform/generated/stage_registry.lock.json").read_text(encoding="utf-8")
    )
    return payload["registry_sha256"]


@pytest.fixture
def sample_package(tmp_path: Path, registry_sha: str):
    source = tmp_path / "source"
    source.mkdir()
    (source / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (source / "note.txt").write_text("hello\n", encoding="utf-8")
    builder = ArtifactPackageBuilder(
        artifact_id="artifact_visualization_data_release_01J00000000000000000000000",
        artifact_type="visualization_data_release",
        schema_version="visualization_manifest_v2",
        producer=ArtifactProducer(
            stage_id="release.visualization_data",
            stage_version=1,
            stage_run_id=None,
            registry_sha256=registry_sha,
        ),
        source=ArtifactSource(source_commit="375cfa9"),
    )
    builder.add_file(
        source / "data.csv",
        relative_path="datasets/data.csv",
        row_count=1,
        column_count=2,
    )
    builder.add_file(source / "note.txt", relative_path="README.txt")
    return builder.build()
