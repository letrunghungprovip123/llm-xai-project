from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from research.python.common_ml.certification import certify_freddie_m13
from research.python.common_ml.modeling import run_common_modeling
from research.python.common_ml.preprocessing import run_common_preprocessing
from research.python.common_ml.split import run_common_split
from research.python.datasets.receipts import StageReceipt, write_json_atomic
from tests.research.python.common_ml.test_common_ml_pipeline import _make_fixture


@pytest.fixture(autouse=True)
def _parquet_engine_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def write_pickle(self: pd.DataFrame, path, index: bool = False, **kwargs) -> None:
        frame = self.reset_index(drop=True) if not index else self
        frame.to_pickle(path)
    monkeypatch.setattr(pd.DataFrame, "to_parquet", write_pickle)
    monkeypatch.setattr(pd, "read_parquet", lambda path, **kwargs: pd.read_pickle(path))


def test_freddie_m13_certifies_common_ml_without_freddie_model_branch(tmp_path: Path) -> None:
    ctx = _make_fixture(tmp_path, dataset_id="freddie_sflld_2024")
    split = run_common_split(ctx)
    run_common_preprocessing(ctx)
    run_common_modeling(ctx)
    m12_path = tmp_path / "m12_receipt.json"
    m12 = StageReceipt(
        stage="freddie_preparation_m12",
        stage_version="v1",
        dataset_id="freddie_sflld_2024",
        patch_id="0007",
        input_fingerprints={},
        config_fingerprints={},
        output_fingerprints={},
        invariants={"canonical_bundle_valid": "PASS"},
        status="PASS",
    )
    write_json_atomic(m12_path, m12.to_dict())
    result = certify_freddie_m13(
        workspace=ctx.execution.workspace_root,
        dataset_profile_path=ctx.dataset_profile_path,
        canonical_bundle_path=ctx.canonical_bundle_path,
        m12_receipt_path=m12_path,
        expected_rows=240,
        expected_positives=sum(
            int(v["positive_count"]) for v in __import__("json").loads(
                (ctx.paths.manifest_dir / "common_ml_split_manifest.json").read_text()
            )["split_stats"]["splits"].values()
        ),
        expected_raw_features=6,
    )
    assert result.receipt.status == "PASS"
    assert result.summary["rows"] == split.train_rows + split.valid_rows + split.test_rows
    assert result.summary["best_model"] in {"logistic_regression", "random_forest", "hist_gradient_boosting"}
    assert all(v == "PASS" for v in result.receipt.invariants.values())
