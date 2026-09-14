#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"; source "$ROOT/scripts/research/freddie_m18_m20_common_0014.sh"; freddie_paths "$ROOT"; freddie_assert_no_provider_execution
mkdir -p "$FREDDIE_VALIDATION_LOCK_DIR"
python3 "$ROOT/scripts/research/freddie_validation_input_lock_0018.py" \
  --repo-root "$ROOT" \
  --claims "$FREDDIE_SEMANTIC_V3_DIR/claims_final.jsonl" \
  --generation-index "$FREDDIE_GENERATION_INDEX" \
  --evidence-packages "$FREDDIE_EVIDENCE_PACKAGES" \
  --replay-manifest "$FREDDIE_REPLAY_V2_DIR/claim_finalization_manifest_v2.json" \
  --semantic-manifest "$FREDDIE_SEMANTIC_V3_DIR/semantic_migration_manifest.json" \
  --output "$FREDDIE_VALIDATION_LOCK_DIR/freddie_validation_input_lock.json"
