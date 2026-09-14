#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$ROOT" ]] || { echo "ERROR: run inside llm-xai-next-refactor"; exit 1; }
cd "$ROOT"
CONFIG="${FREDDIE_DOWNSTREAM_CONFIG:-config/research/replication/freddie_sflld_2024_downstream_v1.json}"
[[ -f "$CONFIG" ]] || { echo "ERROR: config missing: $CONFIG"; exit 1; }
read_cfg(){ python3 - "$CONFIG" "$1" <<'PY'
import json,sys
v=json.load(open(sys.argv[1],encoding='utf-8'))
for p in sys.argv[2].split('.'): v=v[p]
print(v)
PY
}
EVIDENCE="$(read_cfg evidence_path)"; CANON="$(read_cfg canonical_output_dir)"; CONTRACT="$(read_cfg contract_output)"; CLAIM_ROOT="$(read_cfg claim_root)"; FINAL_ROOT="$(read_cfg finalization_root)"

echo "============================================================"
echo "M17B FREEZE EXACT 3-MODEL GENERATION RELEASE"
echo "============================================================"
python3 scripts/research/freddie_freeze_generation_release.py --repo-root "$ROOT" --config "$CONFIG"

echo
echo "============================================================"
echo "M18 CANONICALIZE FREDDIE 648 MATRIX"
echo "============================================================"
npx tsx research/ts/replication/freddieDownstreamCanonicalize.ts --repo-root "$ROOT" --config "$CONFIG"
GEN_INDEX="$CANON/generation_index.jsonl"; CANON_EVIDENCE="$CANON/evidence_packages_36.jsonl"

echo
echo "============================================================"
echo "M19 NARRATIVE CONTRACT"
echo "============================================================"
mkdir -p "$(dirname "$CONTRACT")"
[[ ! -e "$CONTRACT" ]] || { echo "ERROR: refusing overwrite: $CONTRACT"; exit 1; }
npm run research:ts -- llm:contract --generation-index "$GEN_INDEX" --evidence "$CANON_EVIDENCE" --output "$CONTRACT"
ROWS="$(wc -l < "$CONTRACT" | tr -d ' ')"; [[ "$ROWS" == "648" ]] || { echo "ERROR: contract rows=$ROWS"; exit 1; }
echo "FREDDIE_NARRATIVE_CONTRACT=PASS rows=648"

echo
echo "============================================================"
echo "M20 CLAIM EXTRACTION BALANCED 18-CELL SMOKE"
echo "============================================================"
SMOKE_ROOT="$CLAIM_ROOT/smoke_18"; SMOKE_INDEX="$SMOKE_ROOT/generation_index_18.jsonl"; SMOKE_CLAIMS="$SMOKE_ROOT/claims.jsonl"; SMOKE_FAILURES="$SMOKE_ROOT/claim_extraction_failures.jsonl"; SMOKE_ATTEMPTS="$SMOKE_ROOT/claim_extraction_attempts.jsonl"
if [[ -d "$SMOKE_ROOT" && -n "$(find "$SMOKE_ROOT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then echo "ERROR: contaminated smoke dir: $SMOKE_ROOT"; exit 1; fi
mkdir -p "$SMOKE_ROOT"
python3 scripts/research/freddie_claim_smoke_subset.py --generation-index "$GEN_INDEX" --output "$SMOKE_INDEX"
export DEEPSEEK_CLAIM_MAX_TOKENS="3000"
npm run research:ts -- llm:claims --generation-index "$SMOKE_INDEX" --claims-output "$SMOKE_CLAIMS" --failures-output "$SMOKE_FAILURES" --attempts-output "$SMOKE_ATTEMPTS" --checkpoint-every 1 --force false --store-raw-responses true
python3 scripts/research/freddie_claim_extraction_acceptance.py --generation-index "$SMOKE_INDEX" --claims "$SMOKE_CLAIMS" --failures "$SMOKE_FAILURES" --attempts "$SMOKE_ATTEMPTS" --expected-canonical 18 --expected-usable 18 --expected-unusable 0 --require-complete --output "$SMOKE_ROOT/acceptance.json"
echo "CLAIM_EXTRACTION_SMOKE=PASS"
[[ "${FREDDIE_STOP_AFTER_SMOKE:-0}" != "1" ]] || { echo "FREDDIE_STOP_AFTER_SMOKE=1"; exit 0; }

echo
echo "============================================================"
echo "M21 FULL CLAIM EXTRACTION — 645 USABLE GENERATIONS"
echo "============================================================"
FULL_ROOT="$CLAIM_ROOT/full"; FULL_CLAIMS="$FULL_ROOT/claims.jsonl"; FULL_FAILURES="$FULL_ROOT/claim_extraction_failures.jsonl"; FULL_ATTEMPTS="$FULL_ROOT/claim_extraction_attempts.jsonl"
if [[ -d "$FULL_ROOT" && -n "$(find "$FULL_ROOT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then echo "ERROR: contaminated full dir: $FULL_ROOT"; exit 1; fi
mkdir -p "$FULL_ROOT"
npm run research:ts -- llm:claims --generation-index "$GEN_INDEX" --claims-output "$FULL_CLAIMS" --failures-output "$FULL_FAILURES" --attempts-output "$FULL_ATTEMPTS" --checkpoint-every 5 --force false --store-raw-responses true
set +e
python3 scripts/research/freddie_claim_extraction_acceptance.py --generation-index "$GEN_INDEX" --claims "$FULL_CLAIMS" --failures "$FULL_FAILURES" --attempts "$FULL_ATTEMPTS" --expected-canonical 648 --expected-usable 645 --expected-unusable 3 --require-complete --output "$FULL_ROOT/acceptance.json"
GATE=$?
set -e
if [[ "$GATE" != "0" ]]; then
  echo "FULL_CLAIM_EXTRACTION=INCOMPLETE"
  echo "Do NOT rerun the cohort and do NOT use --force true."
  echo "Inspect $FULL_ROOT/acceptance.json and stored attempts/failures."
  echo "Raw responses are stored for offline repair before any provider retry."
  exit 2
fi

echo
echo "============================================================"
echo "M22 DETERMINISTIC CLAIM FINALIZATION"
echo "============================================================"
mkdir -p "$FINAL_ROOT"; FINAL_CLAIMS="$FINAL_ROOT/claims_final.jsonl"; FINAL_CHANGES="$FINAL_ROOT/claim_finalization_changes.jsonl"; FINAL_MANIFEST="$FINAL_ROOT/claim_finalization_manifest.json"
for x in "$FINAL_CLAIMS" "$FINAL_CHANGES" "$FINAL_MANIFEST"; do [[ ! -e "$x" ]] || { echo "ERROR: refusing overwrite: $x"; exit 1; }; done
npm run research:ts -- llm:claims-finalize --generation-index "$GEN_INDEX" --claims-input "$FULL_CLAIMS" --attempts-input "$FULL_ATTEMPTS" --failures-input "$FULL_FAILURES" --claims-output "$FINAL_CLAIMS" --changes-output "$FINAL_CHANGES" --manifest-output "$FINAL_MANIFEST"
python3 scripts/research/freddie_atomic_claim_acceptance.py --generation-index "$GEN_INDEX" --claims-final "$FINAL_CLAIMS" --changes "$FINAL_CHANGES" --manifest "$FINAL_MANIFEST" --output "$FINAL_ROOT/freddie_atomic_claim_release_acceptance.json"
echo "============================================================"
echo "FREDDIE_DOWNSTREAM_TO_ATOMIC_CLAIMS=COMPLETE"
echo "CANONICAL_GENERATIONS=648"
echo "USABLE_GENERATIONS=645"
echo "UNUSABLE_GENERATIONS=3"
echo "CLAIMS_FINAL=$FINAL_CLAIMS"
echo "============================================================"
