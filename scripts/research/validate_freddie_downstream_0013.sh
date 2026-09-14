#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"; [[ -n "$ROOT" ]] || { echo "ERROR: run inside repository"; exit 1; }; cd "$ROOT"
CORE="research/ts/canonicalization/buildGenerationIndex.ts"; RUNNER="research/ts/replication/freddieDownstreamCanonicalize.ts"; CONFIG="config/research/replication/freddie_sflld_2024_downstream_v1.json"
python3 - "$CORE" <<'PY'
from pathlib import Path
import sys
text=Path(sys.argv[1]).read_text(encoding='utf-8'); anchor='const usableCount = input.mainRows.filter((row) => row.usable).length;'; start=text.find(anchor)
if start<0: raise SystemExit('PATCH_0013A_ANCHOR=FAIL')
window=text[start:start+700]
for token in ('if (input.strictOfficialCounts)','passCheck("main_matrix_usable_count", 638, usableCount)','passCheck("main_matrix_unusable_count", 10'):
    if token not in window: raise SystemExit('PATCH_0013A_GUARD=FAIL')
print('PATCH_0013A_NON_STRICT_USABILITY=PASS')
PY
python3 -m py_compile scripts/research/freddie_freeze_generation_release.py scripts/research/freddie_claim_smoke_subset.py scripts/research/freddie_claim_extraction_acceptance.py scripts/research/freddie_atomic_claim_acceptance.py
echo "PATCH_0013_PYTHON_COMPILE=PASS"
bash -n scripts/research/run_freddie_downstream_0013.sh
echo "PATCH_0013_BASH_SYNTAX=PASS"
python3 - "$CONFIG" <<'PY'
import json,sys
c=json.load(open(sys.argv[1],encoding='utf-8'))
assert c['dataset_id']=='freddie_sflld_2024'; assert c['expected']['planned_generations']==648; assert c['expected']['usable_generations']==645; assert c['expected']['unusable_generations']==3
assert [x['model_id'] for x in c['sources']]==['qwen3_8b','deepseek_v4_flash','phi4_mini_instruct']; assert [x['expected_usable'] for x in c['sources']]==[216,213,216]
print('PATCH_0013_CONFIG=PASS')
PY
if [[ -f tsconfig.research.json ]]; then npx tsc -p tsconfig.research.json --noEmit; echo "PATCH_0013_RESEARCH_TYPECHECK=PASS"; elif [[ -f tsconfig.json ]]; then npx tsc -p tsconfig.json --noEmit; echo "PATCH_0013_TYPESCRIPT_TYPECHECK=PASS"; else echo "PATCH_0013_TYPESCRIPT_TYPECHECK=SKIPPED_NO_TSCONFIG"; fi
if [[ -f tests/research/ts/replication/m17GenerationPlan.test.ts ]]; then node --test --import tsx tests/research/ts/replication/m17GenerationPlan.test.ts; echo "PATCH_0013_M17_REGRESSION=PASS"; fi
git diff --check -- "$CORE" "$RUNNER" "$CONFIG" scripts/research
echo "PATCH_0013_DIFF_CHECK=PASS"
echo "PATCH_0013_DETERMINISTIC_VALIDATION=PASS"
