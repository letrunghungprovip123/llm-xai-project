from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from research.python.researchops.gates.contracts import GateCheck


@dataclass(frozen=True)
class AdapterResult:
    outcome: str
    expected: dict[str, Any]
    observed: dict[str, Any]
    checks: tuple[GateCheck, ...]
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdapterContext:
    gate_id: str
    report_path: Path
    artifact_id: str
    artifact_type: str
    manifest_sha256: str


class GateAdapter(Protocol):
    adapter_id: str
    adapter_version: int

    def evaluate(self, context: AdapterContext) -> AdapterResult: ...
