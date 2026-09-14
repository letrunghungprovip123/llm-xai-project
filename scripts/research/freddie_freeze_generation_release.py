#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, tempfile
from pathlib import Path
from typing import Any

MODELS=("qwen3_8b","deepseek_v4_flash","phi4_mini_instruct")
LEVELS=("S0","S1","S2","S3","S4","S5")

def load_json(path: Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise RuntimeError(f"{path} must contain an object")
    return value

def read_jsonl(path: Path)->list[dict[str,Any]]:
    rows=[]
    for n,raw in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        raw=raw.strip()
        if not raw: continue
        value=json.loads(raw)
        if not isinstance(value,dict): raise RuntimeError(f"Object expected: {path}:{n}")
        rows.append(value)
    return rows

def sha256_file(path: Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def is_usable(row:dict[str,Any])->bool:
    runtime=row.get("runtime_metrics") or {}; schema=row.get("schema_metrics") or {}
    return runtime.get("status")=="SUCCESS" and runtime.get("empty_response") is not True and runtime.get("truncated_response") is not True and runtime.get("finish_reason")!="length" and schema.get("raw_json_parse_success") is True and schema.get("schema_valid") is True and schema.get("missing_required_field_count")==0 and schema.get("validation_error_count")==0 and row.get("parsed_output") is not None

def case_id(row:dict[str,Any])->str|None:
    if isinstance(row.get("case_id"),str) and row["case_id"]: return row["case_id"]
    meta=row.get("case_metadata")
    if isinstance(meta,dict):
        for key in ("case_id","customer_id","source_entity_id"):
            if meta.get(key) is not None: return str(meta[key])
    snap=row.get("input_snapshot")
    if isinstance(snap,dict) and isinstance(snap.get("case"),dict) and snap["case"].get("case_id") is not None:
        return str(snap["case"]["case_id"])
    return None

def choose_generation(root:Path,model:str)->tuple[Path,list[dict[str,Any]]]:
    candidates=[]
    for p in root.rglob("generations.jsonl"):
        try: rows=read_jsonl(p)
        except Exception: continue
        if len(rows)==216 and {str(r.get("model_id")) for r in rows}=={model}: candidates.append((p,rows))
    if not candidates: raise RuntimeError(f"{model}: no valid 216-row generations.jsonl")
    by_hash={}
    for p,rows in candidates: by_hash.setdefault(sha256_file(p),[]).append((p,rows))
    if len(by_hash)!=1: raise RuntimeError(f"{model}: multiple non-identical valid generation artifacts")
    items=next(iter(by_hash.values())); items.sort(key=lambda x:(len(x[0].parts),str(x[0])))
    return items[0]

def choose_prompts(root:Path,generations:list[dict[str,Any]],model:str)->tuple[Path,list[dict[str,Any]]]:
    expected={str(r.get("prompt_id")) for r in generations}; candidates=[]
    seen=set()
    for name in ("prompt_instances.jsonl","prompts.jsonl"):
        for p in root.rglob(name):
            if p in seen: continue
            seen.add(p)
            try: rows=read_jsonl(p)
            except Exception: continue
            if len(rows)==216 and {str(r.get("prompt_id")) for r in rows}==expected: candidates.append((p,rows))
    if not candidates: raise RuntimeError(f"{model}: no prompt artifact matches all 216 generation prompt IDs")
    by_hash={}
    for p,rows in candidates: by_hash.setdefault(sha256_file(p),[]).append((p,rows))
    if len(by_hash)!=1: raise RuntimeError(f"{model}: multiple non-identical matching prompt artifacts")
    items=next(iter(by_hash.values())); items.sort(key=lambda x:(len(x[0].parts),str(x[0])))
    return items[0]

def verify_generations(rows,model,revision,expected_usable):
    if len(rows)!=216: raise RuntimeError(f"{model}: rows != 216")
    if {str(r.get("model_id")) for r in rows}!={model}: raise RuntimeError(f"{model}: wrong model IDs")
    revisions={r.get("model_revision") for r in rows}
    if revisions!={revision}: raise RuntimeError(f"{model}: revision mismatch {revisions}")
    levels={x:0 for x in LEVELS}
    for r in rows:
        level=str(r.get("evidence_level"))
        if level not in levels: raise RuntimeError(f"{model}: bad level {level}")
        levels[level]+=1
    if any(v!=36 for v in levels.values()): raise RuntimeError(f"{model}: level counts {levels}")
    irs={str(r.get("source_ir_id")) for r in rows}; cases={x for r in rows if (x:=case_id(r))}
    if len(irs)!=36: raise RuntimeError(f"{model}: source_ir count {len(irs)}")
    if cases and len(cases)!=36: raise RuntimeError(f"{model}: case count {len(cases)}")
    if len({str(r.get("generation_id")) for r in rows})!=216: raise RuntimeError(f"{model}: duplicate generation_id")
    if len({str(r.get("prompt_id")) for r in rows})!=216: raise RuntimeError(f"{model}: duplicate prompt_id")
    runtime=sum((r.get("runtime_metrics") or {}).get("status")=="SUCCESS" for r in rows)
    usable=sum(is_usable(r) for r in rows)
    if runtime!=216: raise RuntimeError(f"{model}: runtime success {runtime}")
    if usable!=expected_usable: raise RuntimeError(f"{model}: usable expected {expected_usable}, got {usable}")
    return {"records":216,"runtime_success":runtime,"usable":usable,"unusable":216-usable,"source_ir_ids":len(irs),"case_ids":len(cases),"levels":levels}

def verify_prompts(gens,prompts,model):
    by_id={str(r.get("prompt_id")):r for r in prompts}
    if len(by_id)!=216: raise RuntimeError(f"{model}: duplicate/missing prompt IDs")
    mismatches=0
    for g in gens:
        p=by_id.get(str(g.get("prompt_id")))
        if p is None: raise RuntimeError(f"{model}: missing prompt")
        gh=g.get("prompt_message_sha256"); ph=p.get("message_sha256")
        if gh is not None and ph is not None and gh!=ph: mismatches+=1
    if mismatches: raise RuntimeError(f"{model}: prompt hash mismatches {mismatches}")
    return {"records":216,"prompt_hash_mismatch":0}

def materialize_source(uri:str,dst:Path,root:Path):
    if uri.startswith("s3://"):
        dst.mkdir(parents=True,exist_ok=True)
        cmd=["aws","s3","cp",uri.rstrip("/")+"/",str(dst),"--recursive"]
        print("RUN:"," ".join(cmd),flush=True)
        rc=subprocess.run(cmd,cwd=root,check=False).returncode
        if rc: raise RuntimeError(f"S3 download failed exit={rc}")
    else:
        src=Path(uri); src=src if src.is_absolute() else root/src; src=src.resolve()
        if not src.exists(): raise RuntimeError(f"Local source missing: {src}")
        shutil.copytree(src,dst)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--config",required=True); ap.add_argument("--repo-root",default="."); a=ap.parse_args()
    root=Path(a.repo_root).resolve(); cp=Path(a.config); cp=cp if cp.is_absolute() else root/cp; cfg=load_json(cp.resolve())
    if cfg.get("dataset_id")!="freddie_sflld_2024": raise RuntimeError("Refusing non-Freddie config")
    final=root/str(cfg["frozen_source_root"])
    if final.exists():
        mf=final/"source_manifest.json"
        if mf.exists() and load_json(mf).get("status")=="PASS":
            print("FREDDIE_GENERATION_FREEZE=ALREADY_PASS"); print(f"FREEZE_ROOT={final}"); return
        raise RuntimeError(f"Freeze destination exists but is not PASS: {final}")
    final.parent.mkdir(parents=True,exist_ok=True)
    tmp=Path(tempfile.mkdtemp(prefix=".m17b_frozen_tmp_",dir=final.parent)); sources=[]; total=usable_total=0
    try:
        for src_cfg in cfg["sources"]:
            model=str(src_cfg["model_id"])
            if model not in MODELS: raise RuntimeError(f"Unexpected model {model}")
            raw=tmp/"_raw"/model; materialize_source(str(src_cfg["source_uri"]),raw,root)
            gp,grows=choose_generation(raw,model); pp,prows=choose_prompts(raw,grows,model)
            gs=verify_generations(grows,model,str(src_cfg["model_revision"]),int(src_cfg["expected_usable"])); ps=verify_prompts(grows,prows,model)
            md=tmp/model; md.mkdir(parents=True,exist_ok=True); ng=md/"generations.jsonl"; np=md/"prompts.jsonl"; shutil.copy2(gp,ng); shutil.copy2(pp,np)
            rec={"schema_version":"freddie_generation_source_v1","status":"PASS","dataset_id":cfg["dataset_id"],"experiment_id":cfg["experiment_id"],"model_id":model,"run_id":src_cfg["run_id"],"aws_job_id":src_cfg.get("aws_job_id"),"source_uri":src_cfg["source_uri"],"model_revision":src_cfg["model_revision"],"generation_sha256":sha256_file(ng),"prompt_sha256":sha256_file(np),"generation_summary":gs,"prompt_summary":ps}
            (md/"SOURCE.json").write_text(json.dumps(rec,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); sources.append(rec); total+=216; usable_total+=gs["usable"]
        exp=cfg["expected"]
        if total!=int(exp["planned_generations"]) or usable_total!=int(exp["usable_generations"]): raise RuntimeError(f"Overall freeze mismatch {total}/{usable_total}")
        manifest={"schema_version":"freddie_generation_freeze_v1","status":"PASS","dataset_id":cfg["dataset_id"],"experiment_id":cfg["experiment_id"],"protocol_id":cfg["protocol_id"],"protocol_sha256":cfg["protocol_sha256"],"evidence_sha256":cfg["evidence_sha256"],"observed":{"records":total,"usable":usable_total,"unusable":total-usable_total},"sources":sources,"policy":{"raw_generation_content_modified":False,"unusable_generations_preserved":True,"deepseek_eval36_filter_applied":False,"reason":"DeepSeek was generated directly from the frozen Freddie evaluation_36 evidence set."}}
        (tmp/"source_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); shutil.rmtree(tmp/"_raw",ignore_errors=True)
        lines=[]
        for p in sorted(x for x in tmp.rglob("*") if x.is_file()): lines.append(f"{sha256_file(p)}  {p.relative_to(tmp).as_posix()}")
        (tmp/"MANIFEST.sha256").write_text("\n".join(lines)+"\n",encoding="utf-8"); os.replace(tmp,final)
        print("FREDDIE_GENERATION_FREEZE=PASS"); print(f"RECORDS={total}"); print(f"USABLE={usable_total}"); print(f"UNUSABLE={total-usable_total}"); print(f"FREEZE_ROOT={final}")
    except Exception:
        shutil.rmtree(tmp,ignore_errors=True); raise

if __name__=="__main__": main()
