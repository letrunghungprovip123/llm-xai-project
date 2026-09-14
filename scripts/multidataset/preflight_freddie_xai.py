#!/usr/bin/env python3
from __future__ import annotations
import argparse, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT))
from research.python.common_xai.context import CommonXAIRunContext
from research.python.common_xai.certification import preflight_freddie_case_selection

def main() -> int:
    p=argparse.ArgumentParser(description="Preflight exact Freddie six-strata XAI selection before SHAP.")
    p.add_argument("--dataset-profile", type=Path, required=True); p.add_argument("--canonical-bundle", type=Path, required=True)
    p.add_argument("--experiment-id", required=True); p.add_argument("--source-run-id", required=True); p.add_argument("--run-id", required=True)
    p.add_argument("--artifact-root", type=Path); p.add_argument("--cases-per-group", type=int, default=20)
    a=p.parse_args()
    ctx=CommonXAIRunContext.load(dataset_profile_path=a.dataset_profile, canonical_bundle_path=a.canonical_bundle, experiment_id=a.experiment_id, source_run_id=a.source_run_id, run_id=a.run_id, artifact_root=a.artifact_root)
    result=preflight_freddie_case_selection(ctx, a.cases_per_group)
    for group,count in result["group_counts"].items(): print(f"{group}={count}")
    print(f"threshold={result['threshold']} selected={result['selected_count']}/{result['expected_count']}")
    if result["status"] != "PASS": raise SystemExit("FREDDIE_XAI_STRATA_PREFLIGHT=FAIL " + "; ".join(result["warnings"]))
    print("FREDDIE_XAI_STRATA_PREFLIGHT=PASS"); return 0
if __name__ == "__main__": raise SystemExit(main())
