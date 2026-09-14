from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from research.python.metric_engineering.quality import add_quality_metrics
from research.python.statistical_analysis.bootstrap import build_case_bootstrap
from research.python.statistical_analysis.inference import (
    build_paired_tests,
    run_repeated_measures_anova,
)


PRIMARY_METRIC = "end_to_end_faithfulness_yield"
CONDITIONAL_METRICS = [
    "resolved_faithfulness",
    "verifiability",
    "conservative_faithfulness",
]
STATUS_COLUMNS = {
    "SUPPORTED": "supported_count",
    "UNSUPPORTED": "unsupported_count",
    "CONTRADICTED": "contradicted_count",
    "NOT_VERIFIABLE": "not_verifiable_count",
    "NOT_APPLICABLE": "not_applicable_count",
}


def _option_id(frame: pd.DataFrame) -> pd.Series:
    return frame["model_id"].astype(str) + "::" + frame["evidence_level"].astype(str)


def option_summary(frame: pd.DataFrame, metric_id: str, dataset_id: str, lane_id: str) -> pd.DataFrame:
    working = frame.copy()
    working["option_id"] = _option_id(working)
    grouped = working.groupby(["option_id", "model_id", "evidence_level"], as_index=False, sort=False).agg(
        planned_generation_count=("generation_id", "size"),
        usable_generation_count=("usable", "sum"),
        metric_mean=(metric_id, "mean"),
        metric_median=(metric_id, "median"),
        metric_non_null_count=(metric_id, "count"),
    )
    grouped["dataset_id"] = dataset_id
    grouped["lane_id"] = lane_id
    grouped["metric_id"] = metric_id
    grouped["quality_rank"] = grouped["metric_mean"].rank(method="min", ascending=False).astype("Int64")
    return grouped[["dataset_id", "lane_id", "metric_id", "option_id", "model_id", "evidence_level", "planned_generation_count", "usable_generation_count", "metric_non_null_count", "metric_mean", "metric_median", "quality_rank"]]


def population_sensitivity(metrics: pd.DataFrame, complete_ids: list[str], dataset_id: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    complete = metrics.loc[metrics["case_id"].astype(str).isin(set(complete_ids))].copy()
    primary_options = option_summary(metrics, PRIMARY_METRIC, dataset_id, "PRIMARY_PLANNED").rename(columns={"metric_mean":"primary_mean","quality_rank":"primary_rank","metric_non_null_count":"primary_metric_n"})
    complete_options = option_summary(complete, PRIMARY_METRIC, dataset_id, "COMPLETE_CASE").rename(columns={"metric_mean":"complete_case_mean","quality_rank":"complete_case_rank","metric_non_null_count":"complete_case_metric_n"})
    options = primary_options[["dataset_id","option_id","model_id","evidence_level","primary_mean","primary_rank","primary_metric_n"]].merge(
        complete_options[["option_id","complete_case_mean","complete_case_rank","complete_case_metric_n"]], on="option_id", validate="one_to_one"
    )
    options["mean_delta_complete_minus_primary"] = options["complete_case_mean"] - options["primary_mean"]
    options["rank_shift_complete_minus_primary"] = options["complete_case_rank"].astype(int) - options["primary_rank"].astype(int)

    primary_omnibus = run_repeated_measures_anova(metrics, metric_id=PRIMARY_METRIC, analysis_role="PRIMARY_CERTIFIED")
    complete_omnibus = run_repeated_measures_anova(complete, metric_id=PRIMARY_METRIC, analysis_role="SENSITIVITY_COMPLETE_CASE")
    effects = primary_omnibus[["effect","subject_count","p_value_used","partial_eta_squared","significant"]].merge(
        complete_omnibus[["effect","subject_count","p_value_used","partial_eta_squared","significant"]], on="effect", suffixes=("_primary","_complete_case"), validate="one_to_one"
    )
    effects.insert(0,"dataset_id",dataset_id)
    effects["significance_conclusion_stable"] = effects["significant_primary"].astype(bool) == effects["significant_complete_case"].astype(bool)
    effects["partial_eta_squared_delta_complete_minus_primary"] = effects["partial_eta_squared_complete_case"] - effects["partial_eta_squared_primary"]

    primary_pairs = build_paired_tests(metrics, metric_id=PRIMARY_METRIC, analysis_role="PRIMARY_CERTIFIED")
    complete_pairs = build_paired_tests(complete, metric_id=PRIMARY_METRIC, analysis_role="SENSITIVITY_COMPLETE_CASE")
    def ids(frame: pd.DataFrame) -> pd.Series:
        return np.where(
            frame["contrast_family"].eq("model_within_evidence"),
            "model_within_evidence::" + frame["context_evidence_level"].astype(str) + "::" + frame["condition_a_model_id"].astype(str) + "::" + frame["condition_b_model_id"].astype(str),
            "evidence_vs_s0::" + frame["context_model_id"].astype(str) + "::" + frame["condition_a_evidence_level"].astype(str),
        )
    primary_pairs=primary_pairs.assign(contrast_id=ids(primary_pairs))
    complete_pairs=complete_pairs.assign(contrast_id=ids(complete_pairs))
    contrasts=primary_pairs[["contrast_id","contrast_family","mean_difference","adjusted_p_value","significant_adjusted"]].merge(
        complete_pairs[["contrast_id","mean_difference","adjusted_p_value","significant_adjusted"]], on="contrast_id", suffixes=("_primary","_complete_case"), validate="one_to_one"
    )
    contrasts.insert(0,"dataset_id",dataset_id)
    contrasts["direction_primary"] = np.sign(contrasts["mean_difference_primary"].fillna(0.0)).astype(int)
    contrasts["direction_complete_case"] = np.sign(contrasts["mean_difference_complete_case"].fillna(0.0)).astype(int)
    contrasts["direction_stable"] = contrasts["direction_primary"] == contrasts["direction_complete_case"]
    contrasts["significance_conclusion_stable"] = contrasts["significant_adjusted_primary"].astype(bool) == contrasts["significant_adjusted_complete_case"].astype(bool)
    return options, effects, contrasts


def metric_sensitivity(metrics: pd.DataFrame, dataset_id: str, metric_ids: list[str]) -> pd.DataFrame:
    frames=[]
    for metric_id in metric_ids:
        frames.append(option_summary(metrics, metric_id, dataset_id, "METRIC_SENSITIVITY" if metric_id != PRIMARY_METRIC else "PRIMARY_CERTIFIED"))
    output=pd.concat(frames,ignore_index=True)
    primary=output.loc[output["metric_id"].eq(PRIMARY_METRIC),["option_id","quality_rank"]].rename(columns={"quality_rank":"primary_rank"})
    output=output.merge(primary,on="option_id",validate="many_to_one")
    output["rank_shift_vs_primary"] = output["quality_rank"].astype("Int64") - output["primary_rank"].astype("Int64")
    return output


def recompute_claim_exclusion_metrics(base_metrics: pd.DataFrame, claims: pd.DataFrame, excluded: set[str]) -> pd.DataFrame:
    remaining=claims.loc[~claims["claim_type"].astype(str).isin(excluded)].copy()
    counts=(remaining.groupby(["generation_id","validation_status"],dropna=False).size().unstack(fill_value=0))
    result=base_metrics.copy()
    for status,column in STATUS_COLUMNS.items():
        values=counts[status] if status in counts.columns else pd.Series(dtype=int)
        result[column]=result["generation_id"].map(values).fillna(0).astype(int)
    result["total_claims"] = result[list(STATUS_COLUMNS.values())].sum(axis=1)
    result["claim_count"] = result["total_claims"]
    result["applicable_count"] = result["supported_count"] + result["unsupported_count"] + result["contradicted_count"] + result["not_verifiable_count"]
    result["resolved_count"] = result["supported_count"] + result["unsupported_count"] + result["contradicted_count"]
    return add_quality_metrics(result)


def claim_type_sensitivity(base_metrics: pd.DataFrame, claims: pd.DataFrame, dataset_id: str, lanes: list[dict[str,Any]]) -> tuple[pd.DataFrame,pd.DataFrame]:
    present=set(claims["claim_type"].dropna().astype(str).unique())
    option_rows=[]; lane_rows=[]
    primary_summary=None
    for lane in lanes:
        lane_id=str(lane["lane_id"]); excluded={str(x) for x in lane["exclude_claim_types"]}
        if excluded and not excluded.intersection(present):
            lane_rows.append({"dataset_id":dataset_id,"lane_id":lane_id,"status":"NOT_APPLICABLE","claims_before":len(claims),"claims_excluded":0,"claims_after":len(claims)})
            continue
        recomputed=recompute_claim_exclusion_metrics(base_metrics,claims,excluded)
        excluded_count=int(claims["claim_type"].astype(str).isin(excluded).sum())
        summary=option_summary(recomputed,PRIMARY_METRIC,dataset_id,lane_id)
        if lane_id=="ALL_APPLICABLE": primary_summary=summary[["option_id","metric_mean","quality_rank"]].rename(columns={"metric_mean":"all_applicable_mean","quality_rank":"all_applicable_rank"})
        summary["claims_before"]=len(claims); summary["claims_excluded"]=excluded_count; summary["claims_after"]=len(claims)-excluded_count; summary["status"]="COMPUTED"
        option_rows.append(summary)
        lane_rows.append({"dataset_id":dataset_id,"lane_id":lane_id,"status":"COMPUTED","claims_before":len(claims),"claims_excluded":excluded_count,"claims_after":len(claims)-excluded_count})
    options=pd.concat(option_rows,ignore_index=True) if option_rows else pd.DataFrame()
    if primary_summary is not None and not options.empty:
        options=options.merge(primary_summary,on="option_id",validate="many_to_one")
        options["mean_delta_vs_all_applicable"]=options["metric_mean"]-options["all_applicable_mean"]
        options["rank_shift_vs_all_applicable"]=options["quality_rank"].astype(int)-options["all_applicable_rank"].astype(int)
    return options,pd.DataFrame(lane_rows)


def margin_sensitivity(ni_results: pd.DataFrame, assessment: pd.DataFrame, margins: list[dict[str,Any]]) -> tuple[pd.DataFrame,pd.DataFrame]:
    hc=ni_results.loc[ni_results["dataset_id"].astype(str).eq("home_credit_default_risk")].copy()
    fm=ni_results.loc[ni_results["dataset_id"].astype(str).eq("freddie_sflld_2024")].copy()
    hc=hc.rename(columns={"candidate_option_id":"option_id","upper_one_sided_bound_95":"hc_upper"})[["option_id","hc_upper"]]
    fm=fm.rename(columns={"candidate_option_id":"option_id","upper_one_sided_bound_95":"fm_upper"})[["option_id","fm_upper"]]
    base=assessment[["option_id","option_role","both_datasets_hard_gate_pass","robust_eligible"]].merge(hc,on="option_id",how="left",validate="one_to_one").merge(fm,on="option_id",how="left",validate="one_to_one")
    rows=[]; summaries=[]
    for lane in margins:
        margin=float(lane["margin"]); current=base.copy(); current["margin_lane_id"]=lane["lane_id"]; current["analysis_status"]=lane["analysis_status"]
        current["home_credit_non_inferior"] = current["hc_upper"].le(margin + 1e-12).fillna(False)
        current["freddie_non_inferior"] = current["fm_upper"].le(margin + 1e-12).fillna(False)
        current["robust_noninferior"] = current["home_credit_non_inferior"] & current["freddie_non_inferior"]
        current["robust_eligible_at_margin"] = current["robust_noninferior"] & current["both_datasets_hard_gate_pass"].astype(bool) & current["option_role"].ne("CONTROL")
        primary_mask=(current["option_role"]=="PRIMARY_CANDIDATE")&current["robust_eligible_at_margin"]
        fallback_mask=(current["option_role"]=="FALLBACK_ONLY")&current["robust_eligible_at_margin"]
        eligible_mask=current["robust_eligible_at_margin"]
        primary_ids=sorted(current.loc[primary_mask,"option_id"].astype(str).tolist())
        fallback_ids=sorted(current.loc[fallback_mask,"option_id"].astype(str).tolist())
        eligible_ids=sorted(current.loc[eligible_mask,"option_id"].astype(str).tolist())
        primary_count=len(primary_ids); fallback_count=len(fallback_ids)
        pool="PRIMARY" if primary_count else ("FALLBACK" if fallback_count else "NONE")
        summaries.append({
            "margin_lane_id":lane["lane_id"],
            "analysis_status":lane["analysis_status"],
            "margin":margin,
            "robust_primary_candidate_count":primary_count,
            "robust_fallback_candidate_count":fallback_count,
            "active_pool_mode":pool,
            "robust_primary_candidate_ids":"|".join(primary_ids),
            "robust_fallback_candidate_ids":"|".join(fallback_ids),
            "robust_eligible_option_ids":"|".join(eligible_ids),
        })
        rows.append(current)
    return pd.concat(rows,ignore_index=True),pd.DataFrame(summaries)


def canonical_contrast_id(
    contrast_family: str,
    a_model: str,
    a_evidence: str,
    b_model: str,
    b_evidence: str,
) -> str:
    """Return the M27 canonical ID for one frozen planned contrast."""
    if contrast_family == "model_within_evidence":
        if a_evidence != b_evidence:
            raise ValueError("model_within_evidence contrast must share evidence level.")
        return f"model_within_evidence::{a_evidence}::{a_model}::{b_model}"
    if contrast_family == "evidence_vs_s0":
        if a_model != b_model or b_evidence != "S0":
            raise ValueError("evidence_vs_s0 contrast must compare one model against S0.")
        return f"evidence_vs_s0::{a_model}::{a_evidence}"
    raise ValueError(f"Unknown contrast family: {contrast_family}")


def contrast_definitions_from_paired(paired: pd.DataFrame) -> list[dict[str,Any]]:
    rows=[]
    for row in paired.itertuples(index=False):
        cid=canonical_contrast_id(
            str(row.contrast_family),
            str(row.condition_a_model_id),
            str(row.condition_a_evidence_level),
            str(row.condition_b_model_id),
            str(row.condition_b_evidence_level),
        )
        rows.append({"contrast_id":cid,"contrast_family":row.contrast_family,"condition_a":{"model_id":row.condition_a_model_id,"evidence_level":row.condition_a_evidence_level},"condition_b":{"model_id":row.condition_b_model_id,"evidence_level":row.condition_b_evidence_level}})
    return rows


def bootstrap_sensitivity(metrics: pd.DataFrame,dataset_id: str,seeds: list[int],iterations: int,confidence: float) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    paired=build_paired_tests(metrics,metric_id=PRIMARY_METRIC,analysis_role="BOOTSTRAP_REGISTRY")
    defs=contrast_definitions_from_paired(paired)
    option_frames=[]; contrast_frames=[]
    for seed in seeds:
        options,contrasts=build_case_bootstrap(metrics,defs,PRIMARY_METRIC,iterations=iterations,confidence=confidence,seed=seed)
        options.insert(0,"dataset_id",dataset_id); options.insert(1,"sensitivity_seed",seed)
        contrasts.insert(0,"dataset_id",dataset_id); contrasts.insert(1,"sensitivity_seed",seed)
        option_frames.append(options); contrast_frames.append(contrasts)
    option_out=pd.concat(option_frames,ignore_index=True); contrast_out=pd.concat(contrast_frames,ignore_index=True)
    contrast_out["ci_excludes_zero"]=(contrast_out["ci_lower"]>0)|(contrast_out["ci_upper"]<0)
    summary=contrast_out.groupby(["dataset_id","contrast_id"],as_index=False).agg(seed_count=("sensitivity_seed","nunique"),zero_exclusion_state_count=("ci_excludes_zero","nunique"),ci_excludes_zero_all=("ci_excludes_zero","all"))
    summary["bootstrap_boundary_stable"] = summary["zero_exclusion_state_count"].eq(1)
    return option_out,contrast_out,summary
