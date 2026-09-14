#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"; source "$ROOT/scripts/research/freddie_m18_m20_common_0014.sh"; freddie_paths "$ROOT"; freddie_assert_no_provider_execution
mkdir -p "$FREDDIE_M19_PREFLIGHT_DIR"
for f in "$FREDDIE_GENERATION_INDEX" "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claims.jsonl" "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claim_extraction_attempts.jsonl" "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claim_extraction_failures.jsonl"; do freddie_require_file "$f"; done
python3 "$ROOT/scripts/research/freddie_m19a_finalization_replay_preflight_0016.py" \
  --generation-index "$FREDDIE_GENERATION_INDEX" \
  --claims "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claims.jsonl" \
  --attempts "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claim_extraction_attempts.jsonl" \
  --failures "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claim_extraction_failures.jsonl" \
  --output "$FREDDIE_M19_PREFLIGHT_DIR/replay_preflight.json"
