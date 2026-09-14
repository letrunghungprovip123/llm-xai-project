from __future__ import annotations

import pytest

from research.python.common_xai.evidence_certification import analyze_evidence_packages


def _ev(fid: str, concept: str = "c") -> dict:
    return {"feature_id": fid, "concept": concept, "shap_value": 0.1, "abs_shap_value": 0.1}


def _packages(case_count: int = 10, *, collapse: bool = False) -> list[dict]:
    out=[]
    for i in range(case_count):
        cid=f"case-{i}"
        # S1 intentionally contains raw evidence only: no concept metadata.
        s1=[{"feature_id":f"f{x}","shap_value":0.1,"abs_shap_value":0.1} for x in range(1,11)]
        s2=[_ev(f"f{x}") for x in range(1,11)]
        s3=s2[:] if collapse else [_ev(f"f{x}") for x in range(1,5)]
        s4=s3[:] if collapse else [_ev(f"f{x}") for x in range(1,7)]
        levels={"S0":[],"S1":s1,"S2":s2,"S3":s3,"S4":s4,"S5":s4}
        for level,selected in levels.items():
            out.append({"case":{"case_id":cid},"evidence_level":level,"selected_evidence":selected,"prompt_payload":{"target_semantics":{"positive_label":"p","negative_label":"n"}}})
    return out


def test_evidence_separability_passes_non_degenerate_conditions() -> None:
    r=analyze_evidence_packages(_packages())
    assert r.status == "PASS"
    assert r.s1_s3_equal_rate == 0
    assert r.s3_s4_equal_rate == 0


def test_evidence_separability_hard_fails_collapsed_conditions() -> None:
    r=analyze_evidence_packages(_packages(collapse=True))
    assert r.status == "FAIL"
    assert r.s1_s3_equal_rate == 1


def test_evidence_structural_invariant_rejects_s0_features() -> None:
    p=_packages(); p[0]["selected_evidence"]=[_ev("bad")]
    with pytest.raises(RuntimeError, match="S0 contains"):
        analyze_evidence_packages(p)


def test_s1_raw_items_do_not_count_as_unknown_semantics() -> None:
    r=analyze_evidence_packages(_packages())
    assert r.status == "PASS"
    assert r.s1_raw_item_count == 100
    assert r.s1_concept_exposure_count == 0
    assert r.semantic_unknown_concept_count == 0
    assert r.unknown_concept_rate == 0.0


def test_unknown_feature_group_is_counted_on_semantic_levels() -> None:
    packages=_packages()
    s2=next(p for p in packages if p["evidence_level"] == "S2")
    s2["selected_evidence"][0]["concept"]="unknown_feature_group"
    r=analyze_evidence_packages(packages)
    assert r.semantic_unknown_concept_count == 1
    assert r.unknown_concept_rate > 0
    assert r.status == "REVIEW_REQUIRED"


def test_s1_semantic_concept_exposure_is_rejected() -> None:
    packages=_packages()
    s1=next(p for p in packages if p["evidence_level"] == "S1")
    s1["selected_evidence"][0]["concept"]="leverage"
    r=analyze_evidence_packages(packages)
    assert r.s1_concept_exposure_count == 1
    assert r.status == "FAIL"
