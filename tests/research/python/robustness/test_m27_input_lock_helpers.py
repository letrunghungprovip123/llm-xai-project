import pandas as pd
import pytest

from research.python.robustness.common import derive_complete_case_ids, option_ids


def frame() -> pd.DataFrame:
    rows=[]
    for case in ["c1","c2"]:
        for model in ["m1","m2"]:
            for evidence in ["S0","S1"]:
                rows.append({"case_id":case,"model_id":model,"evidence_level":evidence,"usable":not(case=="c2" and model=="m2" and evidence=="S1")})
    return pd.DataFrame(rows)


def test_complete_case_ids_derive_from_full_usability_topology() -> None:
    assert derive_complete_case_ids(frame()) == ["c1"]


def test_option_ids_are_semantic_model_evidence_keys() -> None:
    assert option_ids(frame()) == ["m1::S0","m1::S1","m2::S0","m2::S1"]


def test_duplicate_condition_fails_closed() -> None:
    value=frame()
    value=pd.concat([value,value.iloc[[0]]],ignore_index=True)
    with pytest.raises(ValueError,match="Duplicate"):
        derive_complete_case_ids(value)
