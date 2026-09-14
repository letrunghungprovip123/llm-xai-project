from __future__ import annotations

import io
import json
import zipfile
from pathlib import PurePosixPath

import pandas as pd

from .repository import DashboardRepositoryV3


PAGE_TABLES = {
    "/": ("study_summary", "option_performance", "omnibus_effects", "cross_dataset_option_performance", "cross_dataset_effects", "contrast_concordance", "rank_stability", "findings", "limitations"),
    "/effectiveness": ("option_performance", "metric_sensitivity", "omnibus_effects", "planned_contrasts", "metric_dictionary", "findings", "limitations"),
    "/mechanisms": ("study_summary", "failure_decomposition", "claim_type_profile", "metric_sensitivity", "metric_dictionary", "findings", "limitations"),
    "/decision": ("decision_option_assessment", "noninferiority_results", "cross_dataset_eligibility", "pareto_frontier", "recommendations", "scenario_options", "margin_sensitivity_summary", "findings", "limitations"),
    "/robustness": ("robustness_summary", "population_effect_sensitivity", "population_contrast_sensitivity", "metric_sensitivity", "margin_sensitivity_summary", "recommendation_sensitivity", "metric_dictionary", "findings", "limitations"),
    "/cases": ("case_index", "case_generation_metrics", "case_claim_diagnostics", "case_detail_capabilities"),
    "/methods": ("metric_dictionary", "research_questions", "findings", "limitations", "report_source_index", "visualization_dictionary"),
}


def _filter_scope(repo: DashboardRepositoryV3, name: str, frame: pd.DataFrame, scope: str) -> pd.DataFrame:
    if scope == "CROSS_DATASET":
        return frame
    if "dataset_scope" in frame.columns:
        return frame.loc[frame["dataset_scope"].astype(str).eq(scope)].reset_index(drop=True)
    if "scope" in frame.columns and name == "limitations":
        return frame.loc[frame["scope"].astype(str).isin([scope, "GLOBAL"])].reset_index(drop=True)
    dataset_map = repo.study_table("study_summary", scope)
    dataset_id = str(dataset_map.iloc[0]["dataset_id"])
    if "dataset_id" in frame.columns:
        return frame.loc[frame["dataset_id"].astype(str).eq(dataset_id)].reset_index(drop=True)
    return frame


def resolve_export_scope(path: str, global_scope: object, case_identity: object = None) -> str:
    """Resolve export scope from the page's actual semantic authority.

    Case Explorer owns a local single-study dataset independently of the global
    comparison scope. Methods is a global audit surface and must never be
    silently filtered by the shell scope. Other analytical pages retain the
    global shell scope contract.
    """
    global_value = str(global_scope or "")
    if path == "/methods":
        return "CROSS_DATASET"
    if path == "/cases":
        if isinstance(case_identity, dict):
            local = str(case_identity.get("dataset") or "")
            if local in {"HOME_CREDIT", "FREDDIE"}:
                return local
        raise ValueError("Case export requires a hydrated canonical local dataset identity")
    return global_value if global_value in {"HOME_CREDIT", "FREDDIE", "CROSS_DATASET"} else "CROSS_DATASET"


def build_page_export(repo: DashboardRepositoryV3, path: str, scope: str, locale: str) -> tuple[str, bytes]:
    if path not in PAGE_TABLES:
        raise ValueError(f"Unsupported dashboard export path: {path}")
    repo.validate_scope(scope)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w",compression=zipfile.ZIP_DEFLATED) as zf:
        manifest={"release_id":repo.release.release_id,"parent_release_id":repo.release.parent_release_id,"page":path,"scope":scope,"locale":locale,"scientific_recomputation":False,"tables":[]}
        for name in PAGE_TABLES[path]:
            frame=_filter_scope(repo,name,repo.table(name),scope)
            filename=f"tables/{name}.csv"
            zf.writestr(filename,frame.to_csv(index=False,lineterminator="\n"))
            manifest["tables"].append({"name":name,"rows":len(frame),"path":filename})
        zf.writestr("release_metadata.json",json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
        zf.writestr("README.txt",f"Certified presentation export\nrelease={repo.release.release_id}\npage={path}\nscope={scope}\nlocale={locale}\nNo scientific recomputation is performed by this export.\n")
    safe=path.strip('/').replace('/','_') or 'overview'
    return f"llm_xai_{safe}_{scope.lower()}.zip",stream.getvalue()
