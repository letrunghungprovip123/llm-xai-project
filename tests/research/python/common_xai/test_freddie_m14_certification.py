from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from research.python.common_ml.modeling import run_common_modeling
from research.python.common_ml.preprocessing import run_common_preprocessing
from research.python.common_ml.split import run_common_split
from research.python.common_xai.certification import certify_freddie_m14, preflight_freddie_case_selection
from research.python.common_xai.context import CommonXAIRunContext
from research.python.common_xai.ir_stage import run_common_ir
from research.python.common_xai.xai_stage import run_common_xai
from research.python.datasets.receipts import StageReceipt, write_json_atomic
from tests.research.python.common_ml.test_common_ml_pipeline import _make_fixture


@pytest.fixture(autouse=True)
def _parquet_engine_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def write_pickle(self: pd.DataFrame, path, index: bool = False, **kwargs) -> None:
        frame = self.reset_index(drop=True) if not index else self
        frame.to_pickle(path)
    monkeypatch.setattr(pd.DataFrame, "to_parquet", write_pickle)
    monkeypatch.setattr(pd, "read_parquet", lambda path, **kwargs: pd.read_pickle(path))


def test_freddie_m14_preflight_and_certification_use_common_selector_and_ir(tmp_path: Path) -> None:
    ml = _make_fixture(tmp_path, dataset_id="freddie_sflld_2024")
    # Install Freddie target semantics without changing the common-pipeline fixture structure.
    import json
    profile = json.loads(ml.dataset_profile_path.read_text())
    profile["target"]["prediction_semantics"] = {
        "positive_label": "high_12m_serious_delinquency_risk",
        "negative_label": "low_12m_serious_delinquency_risk",
        "prediction_subject": "rủi ro quá hạn nghiêm trọng của khoản vay thế chấp trong 12 tháng",
        "positive_display_name": "cao",
        "negative_display_name": "thấp",
        "positive_direction_phrase": "tăng rủi ro",
        "negative_direction_phrase": "giảm rủi ro",
    }
    ml.dataset_profile_path.write_text(json.dumps(profile), encoding="utf-8")
    # Rebuild bundle profile hash to keep the scientific contract valid.
    bundle = json.loads(ml.canonical_bundle_path.read_text())
    from research.python.datasets.profile import sha256_json
    bundle["dataset_profile_sha256"] = sha256_json(profile)
    ml.canonical_bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    from research.python.common_ml.context import CommonMLRunContext
    ml = CommonMLRunContext.load(
        dataset_profile_path=ml.dataset_profile_path,
        canonical_bundle_path=ml.canonical_bundle_path,
        experiment_id=ml.experiment_id,
        run_id=ml.run_id,
        project_root=ml.project_root,
    )
    run_common_split(ml); run_common_preprocessing(ml); run_common_modeling(ml)
    ctx = CommonXAIRunContext.load(
        dataset_profile_path=ml.dataset_profile_path,
        canonical_bundle_path=ml.canonical_bundle_path,
        experiment_id=ml.experiment_id,
        source_run_id=ml.run_id,
        run_id="xai-m14-test",
        project_root=ml.project_root,
        artifact_root=ml.artifact_root,
    )
    preflight = preflight_freddie_case_selection(ctx, cases_per_group=1)
    assert preflight["status"] == "PASS"
    assert preflight["selected_count"] == 6
    run_common_xai(ctx, cases_per_group=1)
    run_common_ir(ctx)
    m13_path = tmp_path / "m13.json"
    m13 = StageReceipt(
        stage="freddie_common_ml_m13", stage_version="v1", dataset_id="freddie_sflld_2024", patch_id="0008",
        input_fingerprints={}, config_fingerprints={}, output_fingerprints={}, invariants={"m13": "PASS"}, status="PASS"
    )
    write_json_atomic(m13_path, m13.to_dict())
    result = certify_freddie_m14(
        workspace=ctx.execution.workspace_root,
        dataset_profile_path=ml.dataset_profile_path,
        canonical_bundle_path=ml.canonical_bundle_path,
        m13_receipt_path=m13_path,
        expected_cases_per_group=1,
    )
    assert result.receipt.status == "PASS"
    assert result.summary["case_count"] == 6
