"""Multi-dataset scientific contracts and compatibility adapters."""

from .contracts import (
    CanonicalDatasetBundle,
    DatasetCapabilities,
    DatasetProfile,
    ExperimentProfile,
    TargetContract,
)
from .execution import DatasetExecutionContext
from .identity import canonical_case_id, dataset_scoped_id
from .profile import load_canonical_bundle, load_dataset_profile, load_experiment_profile

__all__ = [
    "CanonicalDatasetBundle",
    "DatasetCapabilities",
    "DatasetExecutionContext",
    "DatasetProfile",
    "ExperimentProfile",
    "TargetContract",
    "canonical_case_id",
    "dataset_scoped_id",
    "load_canonical_bundle",
    "load_dataset_profile",
    "load_experiment_profile",
]
