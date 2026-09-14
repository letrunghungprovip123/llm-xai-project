from __future__ import annotations

import math
from typing import Any

from .contracts import TrackingContract
from .exceptions import MLflowContractError
from .models import ModelCandidate


def _finite(value: Any, *, name: str) -> float:
    try:
        observed = float(value)
    except (TypeError, ValueError) as exc:
        raise MLflowContractError(f"Metric {name} is not numeric") from exc
    if not math.isfinite(observed):
        raise MLflowContractError(f"Metric {name} is not finite")
    return observed


def map_model_metrics(candidate: ModelCandidate, contract: TrackingContract) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for split, source in (("validation", candidate.valid_metrics), ("test", candidate.test_metrics or {})):
        for source_name, value in source.items():
            mapped = contract.metric_mapping.get(source_name)
            if mapped is None:
                continue
            metrics[f"{split}_{mapped}"] = _finite(value, name=f"{split}.{source_name}")
    metrics["training_duration_seconds"] = _finite(
        candidate.training_seconds, name="training_seconds"
    )
    if not {"validation_auroc", "validation_pr_auc", "validation_brier_score"} <= set(metrics):
        raise MLflowContractError(
            f"Required validation metrics missing for {candidate.model_name}"
        )
    return metrics
