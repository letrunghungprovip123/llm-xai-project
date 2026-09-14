from __future__ import annotations

from dataclasses import dataclass

from .client import ExperimentGateway
from .contracts import ExperimentCatalog


@dataclass(frozen=True)
class ExperimentBootstrapResult:
    name: str
    experiment_id: str
    created: bool


def bootstrap_experiments(
    gateway: ExperimentGateway,
    catalog: ExperimentCatalog,
) -> tuple[ExperimentBootstrapResult, ...]:
    results: list[ExperimentBootstrapResult] = []
    for definition in catalog.experiments:
        existing = gateway.get_experiment_by_name(definition.name)
        tags = dict(catalog.default_tags)
        tags["researchops.purpose"] = definition.purpose
        if existing is None:
            experiment_id = gateway.create_experiment(definition.name, tags)
            created = True
        else:
            experiment_id = str(existing.experiment_id)
            created = False
            for key, value in tags.items():
                gateway.set_experiment_tag(experiment_id, key, value)
        results.append(ExperimentBootstrapResult(definition.name, experiment_id, created))
    return tuple(results)
