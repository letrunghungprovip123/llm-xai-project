"""Canonical JSON export tests for Page 3."""

import json
from zipfile import ZipFile
from io import BytesIO

from research.python.dashboard.callbacks.mechanisms import build_mechanisms_archive


def test_mechanisms_archive_contains_nine_certified_figures() -> None:
    payload = build_mechanisms_archive()
    with ZipFile(BytesIO(payload)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert len(manifest["figures"]) == 9
        assert all(item["path"].endswith(".json") for item in manifest["figures"])
