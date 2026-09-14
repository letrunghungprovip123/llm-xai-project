#!/usr/bin/env python3
"""Freeze Freddie M22 outputs and the M23 statistical protocol."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def read_json(path: Path) -> dict[str, Any]:
    v=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(v,dict): raise ValueError(path)
    return v

def artifact(root: Path, path: Path) -> dict[str, Any]:
    path=path.resolve()
    if not path.is_file(): raise FileNotFoundError(path)
    try: display=str(path.relative_to(root.resolve()))
    except ValueError: display=str(path)
    return {'path':display,'sha256':sha(path),'byte_count':path.stat().st_size}

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--repo-root',required=True); ap.add_argument('--analysis-lock',required=True); ap.add_argument('--metric-dir',required=True); ap.add_argument('--protocol',required=True); ap.add_argument('--data-mart-dir',required=True); ap.add_argument('--output',required=True); a=ap.parse_args()
    root=Path(a.repo_root).resolve(); analysis_path=Path(a.analysis_lock).resolve(); metric_dir=Path(a.metric_dir).resolve(); protocol_path=Path(a.protocol).resolve(); mart=Path(a.data_mart_dir).resolve(); output=Path(a.output).resolve()
    analysis=read_json(analysis_path); metric_manifest=read_json(metric_dir/'metric_manifest.json'); metric_validation=read_json(metric_dir/'metric_validation.json'); protocol=read_json(protocol_path)
    if (metric_manifest.get('gate')!='ANALYTICAL_MART_READY' or metric_manifest.get('freddie_gate')!='FREDDIE_METRICS_READY' or not metric_validation.get('passed') or metric_validation.get('exit_gate')!='ANALYTICAL_MART_READY'): raise SystemExit('M23 requires certified M22 metrics.')
    contrasts=protocol['paired_tests']['contrasts']
    if len(contrasts)!=33 or len({c['contrast_id'] for c in contrasts})!=33: raise SystemExit('Statistical protocol must freeze exactly 33 unique contrasts.')
    observed=analysis['observed']; complete_ids=sorted(str(x) for x in observed['complete_case_ids']); unusable_ids=sorted(str(x['generation_id']) for x in observed['unusable_generation_records'])
    expected={
      'generation_rows':int(observed['planned_generations']), 'cases':int(observed['canonical_cases']), 'models':int(observed['models']), 'evidence_levels':int(observed['evidence_conditions']), 'model_evidence_cells':int(observed['models'])*int(observed['evidence_conditions']), 'conditions_per_case':18, 'rows_per_model_evidence_cell':int(observed['canonical_cases']), 'omnibus_tests':3, 'model_within_evidence_contrasts':18, 'evidence_vs_s0_contrasts':15, 'paired_tests':33, 'conditional_paired_tests':99, 'complete_case_omnibus_tests':3, 'complete_case_count':len(complete_ids), 'unusable_generation_count':len(unusable_ids), 'sensitivity_summary_rows':3,
    }
    inputs={'generation_metrics':metric_dir/'generation_metrics.csv','metric_validation':metric_dir/'metric_validation.json','cases':mart/'cases.csv','models':mart/'models.csv','evidence_levels':mart/'evidence_levels.csv','metric_manifest':metric_dir/'metric_manifest.json','option_performance':metric_dir/'option_performance.csv'}
    lock={'schema_version':'freddie_statistical_input_lock_v1','dataset_id':analysis['dataset_id'],'experiment_id':analysis['experiment_id'],'parent_analysis_input_lock':artifact(root,analysis_path),'statistical_protocol':artifact(root,protocol_path),'inputs':{k:artifact(root,v) for k,v in inputs.items()},'expected_counts':expected,'expected_unusable_generation_ids':unusable_ids,'expected_complete_case_ids':complete_ids,'bootstrap':protocol['bootstrap'],'contrast_registry_sha256':hashlib.sha256(json.dumps(contrasts,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'gate':'FREDDIE_STATISTICAL_INPUT_LOCK_READY'}
    encoded=json.dumps(lock,ensure_ascii=False,indent=2,sort_keys=True)+'\n'; output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
      if output.read_text(encoding='utf-8')==encoded: print('FREDDIE_M23A_STATISTICAL_INPUT_LOCK=ALREADY_CERTIFIED'); return 0
      raise SystemExit(f'Refusing to overwrite different statistical input lock: {output}')
    output.write_text(encoded,encoding='utf-8'); print(f"FREDDIE_M23A_STATISTICAL_INPUT_LOCK=PASS cases={expected['cases']} complete_cases={expected['complete_case_count']} contrasts=33 bootstrap={lock['bootstrap']['iterations']}"); return 0
if __name__=='__main__': raise SystemExit(main())
