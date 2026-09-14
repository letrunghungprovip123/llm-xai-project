from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from research.python.robustness.common import read_json, record_file, repo_relative, resolve_record, sha256_file

M28_RELATIVE = Path("data/reports/llm_validation/multidataset_replication_v1/certified_analytical_release_v1")
M29_LOCK_RELATIVE = Path("data/reports/llm_validation/multidataset_replication_v1/m29_visualization_input_lock_v1/multidataset_visualization_input_lock.json")
M29_RELEASE_RELATIVE = Path("data/reports/llm_validation/multidataset_replication_v1/visualization_v3")


def m28_dir(root: Path) -> Path: return root / M28_RELATIVE

def m29_lock_path(root: Path) -> Path: return root / M29_LOCK_RELATIVE

def m29_release_dir(root: Path) -> Path: return root / M29_RELEASE_RELATIVE


def visualization_source_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    d=root/"research/python/visualization_v3"
    if d.is_dir(): files.update(p for p in d.glob("*.py") if p.is_file())
    for name in ["multidataset_visualization_v3.json"]:
        p=root/"config/research/replication"/name
        if p.is_file(): files.add(p)
    for pattern in ["*m29*0036*", "*m29*0037*", "run_multidataset_wave_0036_0039.sh"]:
        files.update(p for p in (root/"scripts/research").glob(pattern) if p.is_file())
    return sorted(files,key=lambda p:repo_relative(root,p))


def build_source_identity(root: Path) -> dict[str,Any]:
    digest=hashlib.sha256(); rows=[]
    for p in visualization_source_files(root):
        rel=repo_relative(root,p); sha=sha256_file(p); size=p.stat().st_size
        rows.append({"path":rel,"sha256":sha,"byte_count":size})
        digest.update(f"{rel}\0{sha}\0{size}\n".encode())
    return {"strategy":"explicit_m29_artifact_relevant_file_hashes","file_count":len(rows),"files":rows,"source_tree_identity_sha256":digest.hexdigest()}


def load_m28_manifest(root: Path) -> dict[str,Any]:
    p=m28_dir(root)/"analytical_release_manifest.json"
    manifest=read_json(p)
    if manifest.get("gate")!="CERTIFIED_MULTIDATASET_ANALYTICAL_RELEASE_READY" or manifest.get("scientific_truth_frozen") is not True:
        raise ValueError("M29 requires certified frozen M28 analytical truth.")
    for name,rec in manifest.get("files",{}).items():
        q=m28_dir(root)/name
        if not q.is_file() or sha256_file(q)!=rec.get("sha256") or q.stat().st_size!=int(rec.get("byte_count",-1)):
            raise ValueError(f"M28 release artifact drift: {name}")
    return manifest


def authorized_sources(root: Path) -> dict[str,dict[str,Any]]:
    frame=pd.read_csv(m28_dir(root)/"source_artifact_index.csv")
    required={"source_artifact_id","source_path","source_sha256","byte_count"}
    if required-set(frame.columns): raise ValueError("M28 source artifact index schema mismatch.")
    if frame["source_artifact_id"].astype(str).duplicated().any(): raise ValueError("Duplicate M28 source artifact id.")
    output={}
    for row in frame.to_dict(orient="records"):
        aid=str(row["source_artifact_id"]); p=root/str(row["source_path"])
        if not p.is_file() or sha256_file(p)!=str(row["source_sha256"]) or p.stat().st_size!=int(row["byte_count"]):
            raise ValueError(f"M28-authorized source drift: {aid}")
        output[aid]={"path":repo_relative(root,p),"sha256":str(row["source_sha256"]),"byte_count":int(row["byte_count"])}
    return output


def read_authorized_csv(root: Path,sources: dict[str,dict[str,Any]],artifact_id: str) -> pd.DataFrame:
    if artifact_id not in sources: raise ValueError(f"Source not authorized by M28: {artifact_id}")
    p=resolve_record(root,sources[artifact_id],artifact_id)
    return pd.read_csv(p,low_memory=False)


def stable_json(path: Path,payload: Any) -> None:
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
