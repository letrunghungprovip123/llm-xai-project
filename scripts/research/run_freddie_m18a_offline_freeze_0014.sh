#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
# shellcheck source=freddie_m18_m20_common_0014.sh
source "$ROOT/scripts/research/freddie_m18_m20_common_0014.sh"
freddie_paths "$ROOT"
freddie_assert_no_provider_execution

INPUT_DIR="${FREDDIE_WORK_INPUT_DIR:-$ROOT/.researchops/manual_inputs/freddie_claim_work_20260819}"
mkdir -p "$FREDDIE_OFFLINE_FREEZE_DIR"

for f in \
  "$FREDDIE_GENERATION_INDEX" \
  "$FREDDIE_HISTORICAL_CLAIMS" \
  "$FREDDIE_HISTORICAL_FAILURES" \
  "$INPUT_DIR/batch01_input.jsonl" "$INPUT_DIR/batch01_responses.jsonl" \
  "$INPUT_DIR/batch02_input.jsonl" "$INPUT_DIR/batch02_responses.jsonl" \
  "$INPUT_DIR/batch03_input.jsonl" "$INPUT_DIR/batch03_responses.jsonl" \
  "$INPUT_DIR/batch04_input.jsonl" "$INPUT_DIR/batch04_responses.jsonl"
do
  freddie_require_file "$f"
done

npx --no-install tsx "$ROOT/research/ts/replication/freddieOfflineResponseFreeze.ts" \
  --generation-index "$FREDDIE_GENERATION_INDEX" \
  --existing-claims "$FREDDIE_HISTORICAL_CLAIMS" \
  --existing-failures "$FREDDIE_HISTORICAL_FAILURES" \
  --batch1-input "$INPUT_DIR/batch01_input.jsonl" \
  --batch1-response "$INPUT_DIR/batch01_responses.jsonl" \
  --batch2-input "$INPUT_DIR/batch02_input.jsonl" \
  --batch2-response "$INPUT_DIR/batch02_responses.jsonl" \
  --batch3-input "$INPUT_DIR/batch03_input.jsonl" \
  --batch3-response "$INPUT_DIR/batch03_responses.jsonl" \
  --batch4-input "$INPUT_DIR/batch04_input.jsonl" \
  --batch4-response "$INPUT_DIR/batch04_responses.jsonl" \
  --responses-output "$FREDDIE_OFFLINE_FREEZE_DIR/offline_claim_responses_447.jsonl" \
  --manifest-output "$FREDDIE_OFFLINE_FREEZE_DIR/offline_claim_responses_manifest.json"
