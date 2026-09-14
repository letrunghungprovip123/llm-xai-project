"""Dependency graph derived from artifact producer-consumer relationships."""

from __future__ import annotations

from collections import defaultdict, deque

from .models import StageRegistry


def producer_map(registry: StageRegistry) -> dict[str, str]:
    producers: dict[str, str] = {}
    for stage in registry.stages:
        if stage.status == "LEGACY":
            continue
        for output in stage.outputs:
            producers[output.contract] = stage.id
    return producers


def dependency_map(registry: StageRegistry) -> dict[str, set[str]]:
    producers = producer_map(registry)
    dependencies: dict[str, set[str]] = {
        stage.id: set() for stage in registry.stages
    }
    for stage in registry.stages:
        for binding in stage.inputs:
            producer = producers.get(binding.contract)
            if producer is not None and producer != stage.id:
                dependencies[stage.id].add(producer)
    return dependencies


def topological_order(registry: StageRegistry) -> list[str]:
    dependencies = dependency_map(registry)
    reverse: dict[str, set[str]] = defaultdict(set)
    indegree = {stage_id: len(values) for stage_id, values in dependencies.items()}
    for stage_id, values in dependencies.items():
        for dependency in values:
            reverse[dependency].add(stage_id)

    queue = deque(sorted(stage_id for stage_id, degree in indegree.items() if degree == 0))
    ordered: list[str] = []
    while queue:
        current = queue.popleft()
        ordered.append(current)
        for child in sorted(reverse[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(ordered) != len(indegree):
        cyclic = sorted(stage_id for stage_id, degree in indegree.items() if degree > 0)
        raise ValueError(f"Stage graph contains a cycle: {cyclic}")
    return ordered


def mermaid_graph(registry: StageRegistry) -> str:
    dependencies = dependency_map(registry)
    lines = ["flowchart LR"]
    for stage in sorted(registry.stages, key=lambda item: item.id):
        node = stage.id.replace(".", "_")
        label = f"{stage.id}\n{stage.verification.success_gate}"
        lines.append(f'  {node}["{label}"]')
    for stage_id, values in sorted(dependencies.items()):
        child = stage_id.replace(".", "_")
        for dependency in sorted(values):
            parent = dependency.replace(".", "_")
            lines.append(f"  {parent} --> {child}")
    return "\n".join(lines) + "\n"
