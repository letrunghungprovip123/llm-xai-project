from __future__ import annotations

import pandas as pd

from scripts.research.multidataset_m25_input_lock_0028 import contrast_id, revision_scope, validate_evidence_mapping


def test_revision_scope_downgrades_mismatch_without_failure() -> None:
    scope, detail = revision_scope(["m"], {"m":["a"]}, {"m":["b"]})
    assert scope == "MODEL_FAMILY_PROTOCOL_REPLICATION"
    assert detail["m"]["status"] == "MISMATCH"


def test_revision_scope_marks_unknown() -> None:
    scope, _ = revision_scope(["m"], {}, {"m":["b"]})
    assert scope == "MODEL_REVISION_UNKNOWN"


def _mapping(level: str, roles: list[str], **signature: object) -> list[dict[str, object]]:
    return [{
        "evidence_level":level,
        "canonical_role":level,
        "accepted_roles":roles,
        "expected_signature":signature,
    }]


def _row(level: str, role: str, **signature: object) -> pd.DataFrame:
    return pd.DataFrame([{"evidence_level":level,"intended_role":role,**signature}])


def test_evidence_mapping_accepts_s0_alias_with_matching_signature() -> None:
    signature={
        "semantic_guidance_level":"none",
        "structural_guidance_level":"low",
        "safe_phrase_available":False,
        "adaptive_selection":False,
        "concept_evidence_available":False,
        "backend_skeleton_available":False,
    }
    result=validate_evidence_mapping(_row("S0","baseline",**signature),_mapping("S0",["baseline","prediction_only_control"],**signature),"hc")
    assert result["passed"]


def test_evidence_mapping_accepts_authoritative_s4_role_alias() -> None:
    signature={
        "semantic_guidance_level":"high",
        "structural_guidance_level":"medium",
        "safe_phrase_available":True,
        "adaptive_selection":True,
        "concept_evidence_available":True,
        "backend_skeleton_available":False,
    }
    result=validate_evidence_mapping(_row("S4","rich_evidence_stress_test",**signature),_mapping("S4",["rich_evidence_stress_test","rich_concept_aware"],**signature),"hc")
    assert result["passed"]


def test_evidence_mapping_accepts_authoritative_s5_role_alias() -> None:
    signature={
        "semantic_guidance_level":"high",
        "structural_guidance_level":"high",
        "safe_phrase_available":True,
        "adaptive_selection":True,
        "concept_evidence_available":True,
        "backend_skeleton_available":True,
    }
    result=validate_evidence_mapping(_row("S5","controlled_rendering",**signature),_mapping("S5",["controlled_rendering","backend_skeleton"],**signature),"hc")
    assert result["passed"]


def test_evidence_mapping_rejects_role_alias_when_structure_is_wrong() -> None:
    expected={
        "semantic_guidance_level":"high",
        "structural_guidance_level":"medium",
        "safe_phrase_available":True,
        "adaptive_selection":True,
        "concept_evidence_available":True,
        "backend_skeleton_available":False,
    }
    observed={**expected,"backend_skeleton_available":True}
    result=validate_evidence_mapping(_row("S4","rich_evidence_stress_test",**observed),_mapping("S4",["rich_evidence_stress_test","rich_concept_aware"],**expected),"hc")
    assert not result["passed"]
    assert result["levels"]["S4"]["role_compatible"] is True
    assert result["levels"]["S4"]["signature_mismatches"]==["backend_skeleton_available"]


def test_evidence_mapping_rejects_unknown_role_even_when_structure_matches() -> None:
    signature={
        "semantic_guidance_level":"high",
        "structural_guidance_level":"medium",
        "safe_phrase_available":True,
        "adaptive_selection":True,
        "concept_evidence_available":True,
        "backend_skeleton_available":False,
    }
    result=validate_evidence_mapping(_row("S4","unexpected_role",**signature),_mapping("S4",["rich_evidence_stress_test","rich_concept_aware"],**signature),"hc")
    assert not result["passed"]
    assert result["levels"]["S4"]["signature_compatible"] is True
    assert result["levels"]["S4"]["role_compatible"] is False


def test_contrast_id_is_stable_for_model_contrast() -> None:
    row=pd.Series({"contrast_family":"model_within_evidence","context_evidence_level":"S2","condition_a_model_id":"a","condition_b_model_id":"b","context_model_id":None,"condition_a_evidence_level":"S2"})
    assert contrast_id(row)=="model_within_evidence::S2::a::b"


def test_evidence_mapping_accepts_authoritative_common_roles_for_all_levels() -> None:
    mapping=[
        {"evidence_level":"S0","canonical_role":"PREDICTION_ONLY_CONTROL","accepted_roles":["baseline","prediction_only_control"],"expected_signature":{"semantic_guidance_level":"none","structural_guidance_level":"low","safe_phrase_available":False,"adaptive_selection":False,"concept_evidence_available":False,"backend_skeleton_available":False}},
        {"evidence_level":"S1","canonical_role":"INDEPENDENT_SYNTHESIS_BASELINE","accepted_roles":["independent_synthesis_baseline"],"expected_signature":{"semantic_guidance_level":"none","structural_guidance_level":"low","safe_phrase_available":False,"adaptive_selection":False,"concept_evidence_available":False,"backend_skeleton_available":False}},
        {"evidence_level":"S2","canonical_role":"SEMANTIC_GROUNDING","accepted_roles":["semantic_grounding"],"expected_signature":{"semantic_guidance_level":"high","structural_guidance_level":"low","safe_phrase_available":True,"adaptive_selection":False,"concept_evidence_available":False,"backend_skeleton_available":False}},
        {"evidence_level":"S3","canonical_role":"ADAPTIVE_COMPACT","accepted_roles":["adaptive_compact"],"expected_signature":{"semantic_guidance_level":"high","structural_guidance_level":"medium","safe_phrase_available":True,"adaptive_selection":True,"concept_evidence_available":False,"backend_skeleton_available":False}},
        {"evidence_level":"S4","canonical_role":"RICH_CONCEPT_AWARE","accepted_roles":["rich_evidence_stress_test","rich_concept_aware"],"expected_signature":{"semantic_guidance_level":"high","structural_guidance_level":"medium","safe_phrase_available":True,"adaptive_selection":True,"concept_evidence_available":True,"backend_skeleton_available":False}},
        {"evidence_level":"S5","canonical_role":"BACKEND_SKELETON","accepted_roles":["controlled_rendering","backend_skeleton"],"expected_signature":{"semantic_guidance_level":"high","structural_guidance_level":"high","safe_phrase_available":True,"adaptive_selection":True,"concept_evidence_available":True,"backend_skeleton_available":True}},
    ]
    rows=[]
    authoritative_roles={"S0":"baseline","S1":"independent_synthesis_baseline","S2":"semantic_grounding","S3":"adaptive_compact","S4":"rich_evidence_stress_test","S5":"controlled_rendering"}
    for entry in mapping:
        rows.append({"evidence_level":entry["evidence_level"],"intended_role":authoritative_roles[entry["evidence_level"]],**entry["expected_signature"]})
    result=validate_evidence_mapping(pd.DataFrame(rows),mapping,"common")
    assert result["passed"]
    assert result["incompatible_levels"]==[]


def test_evidence_mapping_rejects_duplicate_level_rows() -> None:
    signature={"semantic_guidance_level":"none","structural_guidance_level":"low","safe_phrase_available":False,"adaptive_selection":False,"concept_evidence_available":False,"backend_skeleton_available":False}
    frame=pd.concat([_row("S0","baseline",**signature),_row("S0","baseline",**signature)],ignore_index=True)
    result=validate_evidence_mapping(frame,_mapping("S0",["baseline","prediction_only_control"],**signature),"dup")
    assert not result["passed"]
    assert result["duplicate_levels"]==["S0"]
