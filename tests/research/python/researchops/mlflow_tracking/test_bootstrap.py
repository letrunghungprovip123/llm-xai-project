from dataclasses import dataclass

from research.python.researchops.mlflow_tracking.bootstrap import bootstrap_experiments
from research.python.researchops.mlflow_tracking.contracts import load_experiment_catalog


@dataclass
class _Experiment:
    experiment_id: str


class FakeGateway:
    def __init__(self):
        self.experiments = {}
        self.tags = {}

    def get_experiment_by_name(self, name):
        return self.experiments.get(name)

    def create_experiment(self, name, tags):
        experiment_id = str(len(self.experiments) + 1)
        self.experiments[name] = _Experiment(experiment_id)
        self.tags[experiment_id] = dict(tags)
        return experiment_id

    def set_experiment_tag(self, experiment_id, key, value):
        self.tags.setdefault(experiment_id, {})[key] = value


def test_bootstrap_is_idempotent_and_repairs_tags():
    gateway = FakeGateway()
    catalog = load_experiment_catalog()
    first = bootstrap_experiments(gateway, catalog)
    second = bootstrap_experiments(gateway, catalog)
    assert len(first) == 6
    assert all(item.created for item in first)
    assert all(not item.created for item in second)
    assert len(gateway.experiments) == 6
    assert all("researchops.source_of_truth" in tags for tags in gateway.tags.values())
