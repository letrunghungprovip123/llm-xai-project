#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, shutil, tempfile
from pathlib import Path
from research.python.robustness.common import read_json, repo_relative, resolve_record, sha256_file
from research.python.visualization_v3.build import build_tables
from research.python.visualization_v3.common import build_source_identity, stable_json
from research.python.visualization_v3.validate import validate_tables

def file_hashes(d): return {p.name:sha256_file(p) for p in sorted(d.iterdir()) if p.is_file()}
def build(root,lock_path,lock,protocol,out):
 if lock.get("gate")!="MULTIDATASET_VISUALIZATION_V3_INPUT_LOCK_READY": raise ValueError("M29B requires certified M29A input lock.")
 resolve_record(root,lock["protocol"],"m29_protocol")
 for group in ["parents","authorized_sources"]:
  for name,rec in lock[group].items(): resolve_record(root,rec,f"{group}::{name}")
 current=build_source_identity(root)
 if current!=lock.get("source_identity"): raise ValueError("M29 source identity drifted after input lock.")
 tables=build_tables(root,lock); validation=validate_tables(root,protocol,lock,tables)
 if not validation["passed"]: raise ValueError(f"M29 visualization validation failed: {validation['checks']}")
 out.mkdir(parents=True,exist_ok=False)
 for name,df in tables.items(): df.to_csv(out/protocol["tables"][name]["file"],index=False,lineterminator="\n")
 release={"schema_version":"multidataset_visualization_v3_release_metadata_v1","release_id":protocol["release_id"],"visualization_version":protocol["visualization_version"],"parent_release_id":lock["m28_release_id"],"replication_scope":lock["m28_replication_scope"],"robust_recommendation_status":lock["m28_robust_recommendation_status"],"dataset_scopes":protocol["allowed_dataset_scopes"],"study_scopes":protocol["study_scopes"],"scientific_recomputation_allowed":False}
 stable_json(out/"release_metadata.json",release); stable_json(out/"visualization_validation.json",validation)
 files={p.name:{"sha256":sha256_file(p),"byte_count":p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()}
 manifest={"schema_version":"multidataset_visualization_v3_manifest_v1","release_id":protocol["release_id"],"producer":"M29B_0037","parent_input_lock":{"path":repo_relative(root,lock_path),"sha256":sha256_file(lock_path)},"parent_release_id":lock["m28_release_id"],"parent_report_number_count":lock["m28_report_number_count"],"replication_scope":lock["m28_replication_scope"],"table_count":len(tables),"files":files,"gate":"MULTIDATASET_VISUALIZATION_DATA_V3_READY"}
 stable_json(out/"visualization_manifest.json",manifest); return manifest

def reverify(root,lock_path,out):
 m=read_json(out/"visualization_manifest.json"); v=read_json(out/"visualization_validation.json")
 if m.get("gate")!="MULTIDATASET_VISUALIZATION_DATA_V3_READY" or v.get("passed") is not True: raise ValueError("Existing M29 release not certified.")
 if m.get("parent_input_lock",{}).get("sha256")!=sha256_file(lock_path): raise ValueError("Existing M29 parent lock drift.")
 for name,rec in m["files"].items():
  p=out/name
  if not p.is_file() or sha256_file(p)!=rec["sha256"] or p.stat().st_size!=int(rec["byte_count"]): raise ValueError(f"Existing M29 artifact drift: {name}")
 return m

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--repo-root",required=True); p.add_argument("--input-lock",required=True); p.add_argument("--output-dir",required=True); a=p.parse_args(); root=Path(a.repo_root).resolve(); lockp=Path(a.input_lock).resolve(); out=Path(a.output_dir).resolve(); lock=read_json(lockp); protocol=read_json(resolve_record(root,lock["protocol"],"protocol"))
 if out.exists():
  m=reverify(root,lockp,out); print(f"MULTIDATASET_M29_VISUALIZATION_DATA_V3=ALREADY_CERTIFIED tables={m['table_count']} report_numbers={m['parent_report_number_count']}"); return 0
 out.parent.mkdir(parents=True,exist_ok=True); x=Path(tempfile.mkdtemp(prefix='.m29a_',dir=out.parent)); shutil.rmtree(x); y=Path(tempfile.mkdtemp(prefix='.m29b_',dir=out.parent)); shutil.rmtree(y)
 try:
  build(root,lockp,lock,protocol,x); build(root,lockp,lock,protocol,y)
  if file_hashes(x)!=file_hashes(y): raise ValueError("M29 deterministic replay mismatch.")
  os.replace(x,out); x=Path('/__promoted__')
 finally:
  if x.exists(): shutil.rmtree(x,ignore_errors=True)
  if y.exists(): shutil.rmtree(y,ignore_errors=True)
 m=read_json(out/"visualization_manifest.json"); print(f"MULTIDATASET_M29_VISUALIZATION_DATA_V3=PASS tables={m['table_count']} report_numbers={m['parent_report_number_count']} scope={m['replication_scope']}"); return 0
if __name__=='__main__': raise SystemExit(main())
