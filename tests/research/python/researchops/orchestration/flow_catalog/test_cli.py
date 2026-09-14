from __future__ import annotations

import json

from research.python.researchops.orchestration.flow_catalog.cli import main


def test_validate_and_compile_check_cli(capsys):
    assert main(["validate"]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["passed"] is True

    assert main(["compile", "--check"]) == 0
    lock = json.loads(capsys.readouterr().out)
    assert lock["passed"] is True


def test_show_includes_topological_order(capsys):
    assert main(["show", "build_evidence_release"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["topological_order"] == [
        "evidence_packages",
        "evaluation_subset",
    ]
