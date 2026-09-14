from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from research.python.robustness.common import read_json, record_file, resolve_record
from .source_identity import analytical_release_source_files, build_source_identity, source_relevant_git_status


def _git(root: Path,*args: str) -> str:
    result=subprocess.run(["git",*args],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
    return result.stdout.strip()


def build_input_lock(root: Path,protocol_path: Path,m27_lock_path: Path,m27_dir: Path) -> dict[str,Any]:
    protocol=read_json(protocol_path)
    if protocol.get("status")!="FROZEN_BEFORE_ANALYTICAL_RELEASE_BUILD" or protocol.get("scientific_recomputation_allowed") is not False: raise ValueError("M28 analytical release protocol is not frozen fail-closed.")
    m27_lock=read_json(m27_lock_path); m27_manifest=read_json(m27_dir/"robustness_manifest.json"); m27_validation=read_json(m27_dir/"robustness_validation.json")
    if m27_lock.get("gate")!="MULTIDATASET_ROBUSTNESS_INPUT_LOCK_READY" or m27_manifest.get("gate")!="MULTIDATASET_ROBUSTNESS_READY" or m27_validation.get("passed") is not True: raise ValueError("M28 requires certified M27.")
    for name,rec in m27_lock["parents"].items(): resolve_record(root,rec,f"m27_parent::{name}")
    for name,rec in m27_lock["inputs"].items(): resolve_record(root,rec,f"m27_input::{name}")
    source_files=analytical_release_source_files(root)
    source_identity=build_source_identity(root,source_files)
    parent_artifacts={
        "m27_input_lock":record_file(root,m27_lock_path),
        "m27_manifest":record_file(root,m27_dir/"robustness_manifest.json"),
        "m27_validation":record_file(root,m27_dir/"robustness_validation.json"),
    }
    for name,rec in m27_lock["parents"].items(): parent_artifacts[name]=rec
    source_artifacts={name:rec for name,rec in m27_lock["inputs"].items()}
    for name in ["robustness_summary.csv","population_effect_sensitivity.csv","population_contrast_sensitivity.csv","metric_sensitivity.csv","margin_sensitivity_summary.csv","recommendation_sensitivity.csv","validator_sensitivity_status.json","template_baseline_status.json","human_calibration_status.json"]:
        parent_artifacts[f"m27::{name}"]=record_file(root,m27_dir/name)
    return {
        "schema_version":"multidataset_analytical_release_input_lock_v1",
        "release_id":protocol["release_id"],
        "producer":"M28A_0034",
        "protocol":record_file(root,protocol_path),
        "contracts":{
            "report_number":record_file(root,root/"contracts/research/report_number_v1.schema.json"),
            "limitation_registry":record_file(root,root/"contracts/research/limitation_registry_v1.schema.json"),
            "finding_registry":record_file(root,root/"contracts/research/finding_registry_v1.schema.json"),
            "report_source_index":record_file(root,root/"contracts/research/report_source_index_v1.schema.json"),
        },
        "parent_artifacts":parent_artifacts,
        "source_artifacts":source_artifacts,
        "source_identity":source_identity,
        "git":{"head":_git(root,"rev-parse","HEAD"),"branch":_git(root,"branch","--show-current"),"status_porcelain":source_relevant_git_status(root, source_files)},
        "provider_execution_allowed":False,
        "scientific_recomputation_allowed":False,
        "gate":"MULTIDATASET_ANALYTICAL_RELEASE_INPUT_LOCK_READY",
    }
