from __future__ import annotations
from pathlib import Path
from typing import Any
import json
import numpy as np
import pandas as pd
from research.python.robustness.common import read_json
from .common import m28_dir

def validate_tables(root:Path,protocol:dict[str,Any],lock:dict[str,Any],tables:dict[str,pd.DataFrame])->dict[str,Any]:
 checks={}; registry=protocol["tables"]
 checks["table_registry_exact"]={"passed":set(tables)==set(registry),"expected":sorted(registry),"observed":sorted(tables)}
 row_errors={}
 for name,spec in registry.items():
  if "expected_rows" in spec and len(tables[name])!=int(spec["expected_rows"]): row_errors[name]={"expected":int(spec["expected_rows"]),"observed":len(tables[name])}
 checks["structural_row_counts"]={"passed":not row_errors,"expected":{},"observed":row_errors}
 checks["option_identity"]={"passed":len(tables["option_performance"][["dataset_scope","option_id"]].drop_duplicates())==36,"expected":36,"observed":len(tables["option_performance"][["dataset_scope","option_id"]].drop_duplicates())}
 checks["case_identity"]={"passed":len(tables["case_index"][["dataset_scope","case_id"]].drop_duplicates())==72,"expected":72,"observed":len(tables["case_index"][["dataset_scope","case_id"]].drop_duplicates())}
 bad_nonfinite=[]
 for name,df in tables.items():
  for col in df.select_dtypes(include=["number"]).columns:
   vals=pd.to_numeric(df[col],errors="coerce").dropna().to_numpy(dtype=float)
   if len(vals) and not np.isfinite(vals).all(): bad_nonfinite.append(f"{name}.{col}")
 checks["finite_numeric_values"]={"passed":not bad_nonfinite,"expected":[],"observed":bad_nonfinite}
 m28=read_json(m28_dir(root)/"report_numbers.json"); ids={r["report_number_id"] for r in m28["records"]}; seen=set()
 for df in tables.values():
  for col in [c for c in df.columns if c.endswith("_report_number_id")]: seen.update(str(v) for v in df[col].dropna())
 orphan=sorted(seen-ids); checks["report_number_referential_integrity"]={"passed":not orphan,"expected":[],"observed":orphan}
 certified=str(lock["m28_robust_recommendation_status"]); rec=tables["recommendations"]; cross=rec.loc[rec["recommendation_scope"].astype(str).eq("CROSS_DATASET_ROBUST")]
 if certified=="NO_ROBUST_RECOMMENDATION": preserved=(len(cross)>=1 and set(cross["status"].astype(str))=={"NO_ROBUST_RECOMMENDATION"})
 else: preserved=len(cross)>=1
 checks["robust_recommendation_preserved"]={"passed":bool(preserved),"expected":certified,"observed":sorted(cross["status"].astype(str).unique()) if len(cross) else []}
 checks["scientific_recomputation_forbidden"]={"passed":protocol.get("scientific_recomputation_allowed") is False,"expected":False,"observed":protocol.get("scientific_recomputation_allowed")}
 failed=sum(not x["passed"] for x in checks.values())
 return {"schema_version":"multidataset_visualization_v3_validation_v1","checks":checks,"failed_check_count":failed,"passed":failed==0,"exit_gate":"MULTIDATASET_VISUALIZATION_DATA_V3_READY" if failed==0 else "MULTIDATASET_VISUALIZATION_DATA_V3_INVALID"}
