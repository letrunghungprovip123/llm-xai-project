import pandas as pd
from research.python.analytical_release.build import _apply_filter, trace_denominator, trace_value


def test_trace_value_direct_and_mean() -> None:
    frame=pd.DataFrame([{"model_id":"m","value":1.0},{"model_id":"x","value":3.0}])
    direct={"report_number_id":"r","source_filter":{"model_id":"m"},"aggregation":"DIRECT_SINGLE_ROW","source_field":"value"}
    mean={"report_number_id":"r2","source_filter":{},"aggregation":"MEAN","source_field":"value"}
    assert trace_value(frame,direct)==1.0
    assert trace_value(frame,mean)==2.0


def test_filter_is_declarative_equality_only() -> None:
    frame=pd.DataFrame([{"scope":"A","value":1},{"scope":"B","value":2}])
    assert len(_apply_filter(frame,{"scope":"A"}))==1


def test_trace_denominator_is_reproduced_from_population_contract() -> None:
    frame=pd.DataFrame([
        {"model_id":"m","evidence_level":"S1","claim_count":2,"usable":True,"resolved_faithfulness":1.0},
        {"model_id":"m","evidence_level":"S1","claim_count":3,"usable":False,"resolved_faithfulness":None},
    ])
    option={"population_id":"OPTION_PLANNED_36","source_filter":{"model_id":"m","evidence_level":"S1"},"source_field":"value"}
    claims={"population_id":"CLAIM_VALIDATION_RESULT","source_filter":{},"source_field":"claim_count"}
    conditional={"population_id":"CONDITIONAL_GENERATION","source_filter":{},"source_field":"resolved_faithfulness"}
    assert trace_denominator(frame,option)==2
    assert trace_denominator(frame,claims)==5
    assert trace_denominator(frame,conditional)==1
