"""Protocol for dataset-specific preparation adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..contracts import CanonicalDatasetBundle


class DatasetPreparationAdapter(Protocol):
    """Dataset-specific code may vary freely; the emitted contract may not."""

    def validate_source(self) -> dict[str, object]: ...

    def build_canonical_bundle(self, output_path: Path | None = None) -> CanonicalDatasetBundle: ...
