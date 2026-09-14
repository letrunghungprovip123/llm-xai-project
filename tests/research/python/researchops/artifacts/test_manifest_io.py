from pathlib import Path

from research.python.researchops.artifacts.manifest import load_manifest, write_manifest


def test_manifest_round_trip_is_canonical(tmp_path: Path, sample_package):
    path = tmp_path / "manifest.json"
    clean = sample_package.manifest.model_copy(update={"metadata": {}})
    write_manifest(path, clean)
    loaded = load_manifest(path)
    assert loaded == clean
    assert path.read_bytes().endswith(b"\n")
