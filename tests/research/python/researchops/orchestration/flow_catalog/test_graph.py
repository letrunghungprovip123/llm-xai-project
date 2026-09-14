from __future__ import annotations

from copy import deepcopy

from research.python.researchops.orchestration.flow_catalog.graph import (
    render_mermaid,
    topological_order,
)
from research.python.researchops.orchestration.flow_catalog.loader import (
    load_flow_catalog,
)
from research.python.researchops.orchestration.flow_catalog.models import (
    FlowCatalog,
    FlowEdge,
)
from research.python.researchops.orchestration.flow_catalog.validator import (
    validate_flow_catalog,
)


def test_training_flow_has_expected_topological_boundary():
    flow = load_flow_catalog().by_id()["train_model_release"]
    order = topological_order(flow)

    assert order[0] == "data_audit"
    assert order[-1] == "model_ready"
    assert order.index("model_training") < order.index("model_ready")


def test_cycle_is_detected():
    payload = deepcopy(load_flow_catalog().model_dump(mode="json"))
    flow = next(item for item in payload["flows"] if item["id"] == "train_model_release")
    flow["edges"].append(
        FlowEdge(
            from_node="model_ready",
            from_output="report",
            to_node="data_audit",
            to_input="raw_data",
        ).model_dump(mode="json")
    )
    # The added edge also has a contract mismatch; cycle detection must still appear.
    report = validate_flow_catalog(FlowCatalog.model_validate(payload))

    assert not report.passed
    assert any("contains a cycle" in error for error in report.errors)


def test_mermaid_graph_uses_explicit_stage_nodes_and_ports():
    flow = load_flow_catalog().by_id()["build_evidence_release"]
    graph = render_mermaid(flow)

    assert graph.startswith("flowchart LR")
    assert "xai.evidence_packages" in graph
    assert "evidence → evidence" in graph
