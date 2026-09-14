"""Explicit DAG operations for governed flow definitions."""

from __future__ import annotations

from collections import defaultdict, deque

from .models import FlowDefinition


def dependency_map(flow: FlowDefinition) -> dict[str, set[str]]:
    dependencies = {node.node_id: set() for node in flow.nodes}
    for edge in flow.edges:
        dependencies.setdefault(edge.to_node, set()).add(edge.from_node)
        dependencies.setdefault(edge.from_node, set())
    return dependencies


def topological_order(flow: FlowDefinition) -> list[str]:
    dependencies = dependency_map(flow)
    reverse: dict[str, set[str]] = defaultdict(set)
    indegree = {node: len(parents) for node, parents in dependencies.items()}
    for node, parents in dependencies.items():
        for parent in parents:
            reverse[parent].add(node)
    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    result: list[str] = []
    while queue:
        current = queue.popleft()
        result.append(current)
        for child in sorted(reverse[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(result) != len(dependencies):
        remaining = sorted(node for node, degree in indegree.items() if degree > 0)
        raise ValueError(f"Flow {flow.id} contains a cycle involving {remaining}")
    return result


def render_text(flow: FlowDefinition) -> str:
    lines = [f"Flow: {flow.id} v{flow.version}"]
    incoming: dict[str, list[str]] = defaultdict(list)
    for edge in flow.edges:
        incoming[edge.to_node].append(edge.from_node)
    nodes = {node.node_id: node for node in flow.nodes}
    for node_id in topological_order(flow):
        node = nodes[node_id]
        parents = ", ".join(sorted(set(incoming[node_id]))) or "<flow-input>"
        lines.append(
            f"  {node_id} [{node.stage_id}] queue={node.work_queue} <- {parents}"
        )
    return "\n".join(lines)


def render_mermaid(flow: FlowDefinition) -> str:
    lines = ["flowchart LR"]
    for node in flow.nodes:
        suffix = "\\noptional" if not node.required else ""
        lines.append(
            f'  {node.node_id}["{node.stage_id}{suffix}"]'
        )
    for edge in flow.edges:
        lines.append(
            f"  {edge.from_node} -- {edge.from_output} → {edge.to_input} --> {edge.to_node}"
        )
    return "\n".join(lines)
