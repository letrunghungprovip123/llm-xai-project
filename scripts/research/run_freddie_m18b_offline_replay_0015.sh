#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m18_m20_common_0014.sh"
freddie_paths "$ROOT"
freddie_assert_no_provider_execution
mkdir -p "$FREDDIE_EFFECTIVE_EXTRACTION_DIR"
for f in "$FREDDIE_GENERATION_INDEX" "$FREDDIE_HISTORICAL_CLAIMS" "$FREDDIE_HISTORICAL_ATTEMPTS" "$FREDDIE_HISTORICAL_FAILURES" "$FREDDIE_OFFLINE_FREEZE_DIR/offline_claim_responses_447.jsonl"; do freddie_require_file "$f"; done

npx --no-install tsx "$ROOT/research/ts/replication/freddieOfflineClaimReplay.ts" \
  --generation-index "$FREDDIE_GENERATION_INDEX" \
  --historical-claims "$FREDDIE_HISTORICAL_CLAIMS" \
  --historical-attempts "$FREDDIE_HISTORICAL_ATTEMPTS" \
  --historical-failures "$FREDDIE_HISTORICAL_FAILURES" \
  --offline-responses "$FREDDIE_OFFLINE_FREEZE_DIR/offline_claim_responses_447.jsonl" \
  --claims-output "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claims.jsonl" \
  --attempts-output "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claim_extraction_attempts.jsonl" \
  --failures-output "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claim_extraction_failures.jsonl" \
  --events-output "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/offline_replay_events.jsonl" \
  --manifest-output "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/offline_replay_manifest.json"

python3 "$ROOT/scripts/research/freddie_m18_acceptance_0015.py" \
  --generation-index "$FREDDIE_GENERATION_INDEX" \
  --historical-claims "$FREDDIE_HISTORICAL_CLAIMS" \
  --effective-dir "$FREDDIE_EFFECTIVE_EXTRACTION_DIR"
