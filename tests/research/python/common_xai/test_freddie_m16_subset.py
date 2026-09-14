from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from research.python.datasets.profile import sha256_json
from research.python.datasets.receipts import StageReceipt, write_json_atomic
from research.python.evidence_exposure.select_evaluation_subset import get_case_id, get_stratum
from research.python.evidence_exposure.subset_certification import build_and_certify_freddie_m16
from tests.research.python.common_ml.test_common_ml_pipeline import _make_fixture

STRATA=["top_high_risk","low_risk","true_positive","false_positive","false_negative","near_threshold"]

@pytest.fixture(autouse=True)
def _parquet_engine_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def write_pickle(self: pd.DataFrame, path, index: bool = False, **kwargs) -> None:
        frame = self.reset_index(drop=True) if not index else self
        frame.to_pickle(path)
    monkeypatch.setattr(pd.DataFrame, "to_parquet", write_pickle)
    monkeypatch.setattr(pd, "read_parquet", lambda path, **kwargs: pd.read_pickle(path))


def test_selector_reads_multidataset_case_and_legacy_customer() -> None:
    new={"case":{"case_id":"case-new","case_type":"false_negative"},"source_ir_id":"ir-new"}
    legacy={"source_ir_id":"ir-old","internal_metadata":{"customer":{"case_type":"true_positive"}}}
    assert get_case_id(new)=="case-new" and get_stratum(new)=="false_negative"
    assert get_case_id(legacy)=="ir-old" and get_stratum(legacy)=="true_positive"


def test_freddie_m16_freezes_36_cases_and_216_packages(tmp_path: Path) -> None:
    ctx=_make_fixture(tmp_path,dataset_id="freddie_sflld_2024")
    profile=json.loads(ctx.dataset_profile_path.read_text())
    profile["target"]["prediction_semantics"]={"positive_label":"high_12m_serious_delinquency_risk","negative_label":"low_12m_serious_delinquency_risk","prediction_subject":"rủi ro quá hạn nghiêm trọng của khoản vay thế chấp trong 12 tháng","positive_display_name":"cao","negative_display_name":"thấp","positive_direction_phrase":"tăng","negative_direction_phrase":"giảm"}
    ctx.dataset_profile_path.write_text(json.dumps(profile),encoding="utf-8")
    bundle=json.loads(ctx.canonical_bundle_path.read_text()); bundle["dataset_profile_sha256"]=sha256_json(profile); ctx.canonical_bundle_path.write_text(json.dumps(bundle),encoding="utf-8")
    workspace=tmp_path/"xai-workspace"; evidence_dir=workspace/"data/reports/evidence_exposure"; evidence_dir.mkdir(parents=True)
    packages=[]
    for sidx,stratum in enumerate(STRATA):
        for idx in range(20):
            cid=f"case-{stratum}-{idx:02d}"
            for level in ["S0","S1","S2","S3","S4","S5"]:
                packages.append({"package_id":f"pkg-{cid}-{level}","source_ir_id":f"ir-{cid}","evidence_level":level,"dataset":{"dataset_id":"freddie_sflld_2024"},"case":{"case_id":cid,"case_type":stratum},"internal_metadata":{"case":{"case_id":cid,"case_type":stratum}},"target_semantics":{"positive_label":"high_12m_serious_delinquency_risk","negative_label":"low_12m_serious_delinquency_risk","prediction_subject":"rủi ro quá hạn nghiêm trọng của khoản vay thế chấp trong 12 tháng"},"prompt_payload":{"selection_context":{"normalized_entropy":idx/20,"selected_evidence_count":6,"concept_count":3},"prediction":{"probability":0.5+idx/1000,"threshold":0.5}}})
    input_path=evidence_dir/"evidence_packages_all.jsonl"
    input_path.write_text("".join(json.dumps(p,ensure_ascii=False)+"\n" for p in packages),encoding="utf-8")
    m15_path=tmp_path/"m15.json"; write_json_atomic(m15_path,StageReceipt(stage="freddie_evidence_m15",stage_version="v1",dataset_id="freddie_sflld_2024",patch_id="0010",input_fingerprints={},config_fingerprints={},output_fingerprints={},invariants={"m15":"PASS"},status="PASS").to_dict())
    r=build_and_certify_freddie_m16(workspace=workspace,dataset_profile_path=ctx.dataset_profile_path,canonical_bundle_path=ctx.canonical_bundle_path,m15_receipt_path=m15_path)
    assert r.selected_case_count==36 and r.selected_package_count==216
    assert r.receipt.status=="PASS"
