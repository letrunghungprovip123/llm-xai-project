from pathlib import Path
from research.python.analytical_release.source_identity import build_source_identity


def test_source_identity_depends_on_explicit_file_bytes(tmp_path: Path) -> None:
    a=tmp_path/"a.txt"; b=tmp_path/"b.txt"; a.write_text("a"); b.write_text("b")
    one=build_source_identity(tmp_path,[a,b])
    a.write_text("changed")
    two=build_source_identity(tmp_path,[a,b])
    assert one["source_tree_identity_sha256"] != two["source_tree_identity_sha256"]
    assert one["file_count"] == 2


def test_analytical_release_source_set_ignores_downstream_presentation_source(tmp_path: Path) -> None:
    from research.python.analytical_release.source_identity import analytical_release_source_files

    (tmp_path / "research/python/analytical_release").mkdir(parents=True)
    (tmp_path / "contracts/research").mkdir(parents=True)
    (tmp_path / "scripts/research").mkdir(parents=True)
    (tmp_path / "config/research/replication").mkdir(parents=True)
    (tmp_path / "research/python/analytical_release/build.py").write_text("release")
    (tmp_path / "contracts/research/report_number_v1.schema.json").write_text("{}")
    (tmp_path / "scripts/research/run_multidataset_m28b_analytical_release_0035.py").write_text("m28")
    (tmp_path / "scripts/research/run_multidataset_m29a_visualization_0036.py").write_text("m29")
    (tmp_path / "config/research/replication/multidataset_analytical_release_v1.json").write_text("{}")

    paths={p.relative_to(tmp_path).as_posix() for p in analytical_release_source_files(tmp_path)}
    assert "scripts/research/run_multidataset_m28b_analytical_release_0035.py" in paths
    assert "scripts/research/run_multidataset_m29a_visualization_0036.py" not in paths
