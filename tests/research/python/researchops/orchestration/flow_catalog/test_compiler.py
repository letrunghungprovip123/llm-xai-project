from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml

from research.python.researchops.orchestration.flow_catalog.compiler import (
    compile_payload,
    lock_matches,
)
from research.python.researchops.orchestration.flow_catalog.loader import (
    load_flow_catalog,
)


def test_flow_catalog_json_schema_accepts_checked_in_source():
    raw = yaml.safe_load(Path("config/platform/flows.yaml").read_text(encoding="utf-8"))
    schema = json.loads(
        Path("config/platform/schemas/flow_catalog_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )

    jsonschema.Draft202012Validator(schema).validate(raw)
    assert load_flow_catalog().schema_version == "flow_catalog_v1"


def test_flow_catalog_lock_is_current_and_deterministic():
    first = compile_payload()
    second = compile_payload()

    assert first == second
    assert first["flow_count"] == 15
    assert first["covered_stage_count"] == 42
    assert len(first["catalog_sha256"]) == 64
    assert lock_matches()
