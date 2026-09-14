from research.python.researchops.mlflow_tracking.contracts import load_tracking_contract
from research.python.researchops.mlflow_tracking.metric_mapper import map_model_metrics
from research.python.researchops.mlflow_tracking.models import ModelRegistrySnapshot


def test_metric_mapping_uses_frozen_semantics(training_release_package):
    import json
    payload = json.loads(next(path for key, path in training_release_package.source_files.items() if key.endswith('model_registry.json')).read_text())
    registry = ModelRegistrySnapshot.model_validate(payload)
    selected = next(item for item in registry.models if item.selected_as_best)
    metrics = map_model_metrics(selected, load_tracking_contract())
    assert metrics["validation_auroc"] == 0.75
    assert metrics["test_pr_auc"] == 0.26
    assert metrics["training_duration_seconds"] == 1.5
