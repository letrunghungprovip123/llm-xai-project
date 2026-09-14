from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from research.python.robustness.common import read_json, record_file
from .common import authorized_sources, build_source_identity, load_m28_manifest, m28_dir

REQUIRED_M28_FILES=("report_numbers.json","report_source_index.csv","findings_registry.csv","limitations_registry.csv","research_question_registry.csv","release_metric_dictionary.csv","source_artifact_index.csv","analytical_release_validation.json","analytical_release_manifest.json")


def build_input_lock(root: Path, protocol_path: Path) -> dict[str,Any]:
    protocol=read_json(protocol_path)
    if protocol.get("status")!="FROZEN_BEFORE_VISUALIZATION_V3_BUILD": raise ValueError("M29 visualization protocol not frozen.")
    if protocol.get("scientific_recomputation_allowed") is not False or protocol.get("source_discovery_allowed") is not False: raise ValueError("M29 protocol must forbid scientific recomputation/source discovery.")
    manifest=load_m28_manifest(root); d=m28_dir(root)
    validation=read_json(d/"analytical_release_validation.json")
    if validation.get("passed") is not True: raise ValueError("M28 validation is not certified.")
    parents={name:record_file(root,d/name) for name in REQUIRED_M28_FILES}
    sources=authorized_sources(root)
    report=read_json(d/"report_numbers.json"); records=report.get("records",[])
    scopes=sorted({str(r.get("dataset_scope")) for r in records})
    allowed=set(protocol["allowed_dataset_scopes"])
    if not set(scopes).issubset(allowed): raise ValueError(f"Unknown M28 dataset scope(s): {set(scopes)-allowed}")
    metric_ids=sorted({str(r.get("metric_id")) for r in records})
    metric_dict=set(pd.read_csv(d/"release_metric_dictionary.csv")["metric_id"].astype(str))
    if not set(metric_ids).issubset(metric_dict): raise ValueError("M28 report number metric missing from dictionary.")
    ids=[str(r.get("report_number_id")) for r in records]
    if len(ids)!=len(set(ids)): raise ValueError("Duplicate M28 report number IDs.")
    findings=pd.read_csv(d/"findings_registry.csv")
    robust=findings.loc[findings["finding_type"].astype(str).eq("ROBUST_RECOMMENDATION_STATUS")]
    if len(robust)!=1: raise ValueError("Expected exactly one certified robust-recommendation finding.")
    return {
        "schema_version":"multidataset_visualization_v3_input_lock_v1",
        "release_id":protocol["release_id"],
        "producer":"M29A_0036",
        "protocol":record_file(root,protocol_path),
        "m28_release_id":manifest["release_id"],
        "m28_replication_scope":manifest.get("replication_scope"),
        "m28_report_number_count":len(records),
        "m28_report_number_ids":sorted(ids),
        "m28_metric_ids":metric_ids,
        "m28_scopes":scopes,
        "m28_robust_recommendation_status":str(robust.iloc[0]["status"]),
        "parents":parents,
        "authorized_sources":sources,
        "source_identity":build_source_identity(root),
        "provider_execution_allowed":False,
        "scientific_recomputation_allowed":False,
        "source_discovery_allowed":False,
        "gate":"MULTIDATASET_VISUALIZATION_V3_INPUT_LOCK_READY"
    }
