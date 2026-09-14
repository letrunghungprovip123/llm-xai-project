from pathlib import Path
import json
import pytest
from research.python.visualization_v3.input_lock import build_input_lock

def test_protocol_is_presentation_only():
 p=json.loads(Path("config/research/replication/multidataset_visualization_v3.json").read_text())
 assert p["status"]=="FROZEN_BEFORE_VISUALIZATION_V3_BUILD"
 assert p["scientific_recomputation_allowed"] is False
 assert p["source_discovery_allowed"] is False
 assert p["allowed_dataset_scopes"]==["HOME_CREDIT","FREDDIE","CROSS_DATASET","GLOBAL"]
 assert p["tables"]["option_performance"]["expected_rows"]==36
 assert p["tables"]["planned_contrasts"]["expected_rows"]==66

def test_m29a_uses_only_m28_authorized_sources():
 root=Path.cwd(); lock=build_input_lock(root,root/"config/research/replication/multidataset_visualization_v3.json")
 assert lock["gate"]=="MULTIDATASET_VISUALIZATION_V3_INPUT_LOCK_READY"
 assert lock["source_discovery_allowed"] is False
 assert "m26_dataset_option_assessment" in lock["authorized_sources"]
 assert lock["m28_robust_recommendation_status"] in {"NO_ROBUST_RECOMMENDATION","ROBUST_RECOMMENDATION_AVAILABLE"}

def test_m29a_fails_on_unknown_scope(tmp_path):
 root=Path.cwd(); src=root/"config/research/replication/multidataset_visualization_v3.json"; value=json.loads(src.read_text()); value["allowed_dataset_scopes"]=["HOME_CREDIT"]
 p=tmp_path/"bad.json"; p.write_text(json.dumps(value))
 with pytest.raises(ValueError,match="Unknown M28 dataset scope"):
  build_input_lock(root,p)
