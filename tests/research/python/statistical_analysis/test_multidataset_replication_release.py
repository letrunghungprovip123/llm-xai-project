from __future__ import annotations

from scripts.research.multidataset_m25_replication_0029 import classify


def test_replication_classification_replicated() -> None:
    assert classify(0.10,0.08,0.02,0.18,0.01,0.15)=="REPLICATED"


def test_replication_classification_directional() -> None:
    assert classify(0.10,0.08,-0.02,0.18,0.01,0.15)=="DIRECTIONALLY_REPLICATED"


def test_replication_classification_conflict() -> None:
    assert classify(0.10,-0.08,0.02,0.18,-0.15,-0.01)=="DIRECTION_CONFLICT"


def test_replication_classification_zero_is_inconclusive() -> None:
    assert classify(0.0,0.08,-0.01,0.01,0.01,0.15)=="INCONCLUSIVE"
