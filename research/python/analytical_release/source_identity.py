from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from research.python.robustness.common import repo_relative, sha256_file


def upstream_scientific_source_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    roots = [
        root / "research/python/metric_engineering",
        root / "research/python/statistical_analysis",
        root / "research/python/diagnostics",
        root / "research/python/robustness",
    ]
    for directory in roots:
        if directory.is_dir():
            files.update(p for p in directory.glob("*.py") if p.is_file())
    config_names = [
        "freddie_sflld_2024_analysis_v1.json",
        "freddie_sflld_2024_metric_v1.json",
        "freddie_sflld_2024_statistical_v1.json",
        "freddie_sflld_2024_diagnostics_v1.json",
        "multidataset_replication_v1.json",
        "multidataset_decision_policy_v1.json",
        "multidataset_robustness_v1.json",
        "multidataset_analytical_release_v1.json",
    ]
    for name in config_names:
        path = root / "config/research/replication" / name
        if path.is_file():
            files.add(path)
    script_patterns = [
        "freddie_m21*", "freddie_m22*", "freddie_m23*", "freddie_m24*",
        "run_freddie_m21*", "run_freddie_m22*", "run_freddie_m23*", "run_freddie_m24*",
        "multidataset_m25*", "multidataset_m26*", "multidataset_m27*",
        "run_multidataset_m25*", "run_multidataset_m26*", "run_multidataset_m27*",
    ]
    for pattern in script_patterns:
        files.update(p for p in (root / "scripts/research").glob(pattern) if p.is_file())
    metric_dictionary = root / "config/research/ts-validation/metric_dictionary.json"
    if metric_dictionary.is_file():
        files.add(metric_dictionary)
    return sorted(files, key=lambda p: repo_relative(root, p))


def analytical_release_source_files(root: Path) -> list[Path]:
    """Return the explicit artifact-relevant source set frozen by M28A.

    The set includes upstream scientific computation plus the M28 release compiler,
    schemas, protocol, and wave runner. It intentionally excludes later M29/M30
    presentation code so downstream additions cannot retroactively drift M28.
    """
    files: set[Path] = set(upstream_scientific_source_files(root))
    for directory in [root / "research/python/analytical_release", root / "contracts/research"]:
        if directory.is_dir():
            files.update(p for p in directory.glob("*") if p.is_file())
    scripts = root / "scripts/research"
    if scripts.is_dir():
        files.update(p for p in scripts.glob("*m28*003[45]*") if p.is_file())
        wave_runner = scripts / "run_multidataset_wave_0032_0035.sh"
        if wave_runner.is_file():
            files.add(wave_runner)
    protocol = root / "config/research/replication/multidataset_analytical_release_v1.json"
    if protocol.is_file():
        files.add(protocol)
    return sorted(files, key=lambda p: repo_relative(root, p))

def build_source_identity(root: Path, files: list[Path]) -> dict[str,Any]:
    records=[]; digest=hashlib.sha256()
    for path in sorted(files,key=lambda p:repo_relative(root,p)):
        rel=repo_relative(root,path); file_sha=sha256_file(path); size=path.stat().st_size
        records.append({"path":rel,"sha256":file_sha,"byte_count":size})
        digest.update(rel.encode()); digest.update(b"\0"); digest.update(file_sha.encode()); digest.update(b"\0"); digest.update(str(size).encode()); digest.update(b"\n")
    return {"strategy":"git_head_plus_explicit_artifact_relevant_file_hashes","file_count":len(records),"files":records,"source_tree_identity_sha256":digest.hexdigest()}


def source_relevant_git_status(root: Path, relevant_files: list[Path] | None = None) -> str:
    import subprocess
    result = subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    allowed = None if relevant_files is None else {repo_relative(root, p) for p in relevant_files}
    kept = []
    for line in result.stdout.splitlines():
        path = line[3:] if len(line) >= 4 else line
        normalized = path.replace("\\", "/")
        if normalized.startswith("data/") or normalized.startswith(".researchops/"):
            continue
        if "__pycache__" in normalized or normalized.endswith(".pyc"):
            continue
        if allowed is not None and normalized not in allowed:
            continue
        kept.append(line)
    return "\n".join(kept)
