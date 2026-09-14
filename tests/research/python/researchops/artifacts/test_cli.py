from pathlib import Path

from research.python.researchops.artifacts.cli import main
from research.python.researchops.artifacts.manifest import write_manifest


def test_validate_manifest_cli(tmp_path: Path, sample_package, capsys):
    path = tmp_path / "manifest.json"
    clean = sample_package.manifest.model_copy(update={"metadata": {}})
    write_manifest(path, clean)
    assert main(["validate-manifest", str(path)]) == 0
    assert "ARTIFACT_MANIFEST_VALID" in capsys.readouterr().out
