#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"; source "$ROOT/scripts/research/freddie_m18_m20_common_0014.sh"; freddie_paths "$ROOT"; freddie_assert_no_provider_execution
for f in "$FREDDIE_GENERATION_INDEX" "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claims.jsonl" "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claim_extraction_attempts.jsonl" "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claim_extraction_failures.jsonl" "$FREDDIE_M19_PREFLIGHT_DIR/replay_preflight.json"; do freddie_require_file "$f"; done
mkdir -p "$FREDDIE_REPLAY_V2_DIR" "$FREDDIE_SEMANTIC_V3_DIR" "$FREDDIE_FINALIZATION_ROOT/offline_v1/idempotence/replay_v2" "$FREDDIE_FINALIZATION_ROOT/offline_v1/idempotence/semantic_v3"

# Stage 1: current authoritative stored-response replay finalizer (claims_v2).
npx --no-install tsx "$ROOT/research/ts/claim_finalization/main.ts" \
  --generation-index "$FREDDIE_GENERATION_INDEX" \
  --claims-input "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claims.jsonl" \
  --attempts-input "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claim_extraction_attempts.jsonl" \
  --failures-input "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claim_extraction_failures.jsonl" \
  --claims-output "$FREDDIE_REPLAY_V2_DIR/claims_final_v2.jsonl" \
  --changes-output "$FREDDIE_REPLAY_V2_DIR/claim_finalization_changes_v2.jsonl" \
  --manifest-output "$FREDDIE_REPLAY_V2_DIR/claim_finalization_manifest_v2.json"

# Replay idempotence: use the first final artifact as the next input. The output
# claim bytes must be identical and there must be no changes.
IDEM_REPLAY="$FREDDIE_FINALIZATION_ROOT/offline_v1/idempotence/replay_v2"
npx --no-install tsx "$ROOT/research/ts/claim_finalization/main.ts" \
  --generation-index "$FREDDIE_GENERATION_INDEX" \
  --claims-input "$FREDDIE_REPLAY_V2_DIR/claims_final_v2.jsonl" \
  --attempts-input "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claim_extraction_attempts.jsonl" \
  --failures-input "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claim_extraction_failures.jsonl" \
  --claims-output "$IDEM_REPLAY/claims_final_v2.jsonl" \
  --changes-output "$IDEM_REPLAY/claim_finalization_changes_v2.jsonl" \
  --manifest-output "$IDEM_REPLAY/claim_finalization_manifest_v2.json"
cmp "$FREDDIE_REPLAY_V2_DIR/claims_final_v2.jsonl" "$IDEM_REPLAY/claims_final_v2.jsonl"
[[ ! -s "$IDEM_REPLAY/claim_finalization_changes_v2.jsonl" ]] || { echo "ERROR: replay finalization is not idempotent." >&2; exit 3; }

# Stage 2: Freddie-specific schema-v3 semantic migration. It reuses the active
# classifier/compatibility matrix but intentionally does not apply Home-Credit
# manual correction IDs/260-row fixture.
npx --no-install tsx "$ROOT/research/ts/replication/freddieSemanticMigration.ts" \
  --generation-index "$FREDDIE_GENERATION_INDEX" \
  --claims-v2 "$FREDDIE_REPLAY_V2_DIR/claims_final_v2.jsonl" \
  --claims-output "$FREDDIE_SEMANTIC_V3_DIR/claims_final.jsonl" \
  --changes-output "$FREDDIE_SEMANTIC_V3_DIR/semantic_migration_changes.jsonl" \
  --summary-output "$FREDDIE_SEMANTIC_V3_DIR/semantic_migration_summary.json" \
  --manifest-output "$FREDDIE_SEMANTIC_V3_DIR/semantic_migration_manifest.json"
IDEM_SEM="$FREDDIE_FINALIZATION_ROOT/offline_v1/idempotence/semantic_v3"
npx --no-install tsx "$ROOT/research/ts/replication/freddieSemanticMigration.ts" \
  --generation-index "$FREDDIE_GENERATION_INDEX" \
  --claims-v2 "$FREDDIE_REPLAY_V2_DIR/claims_final_v2.jsonl" \
  --claims-output "$IDEM_SEM/claims_final.jsonl" \
  --changes-output "$IDEM_SEM/semantic_migration_changes.jsonl" \
  --summary-output "$IDEM_SEM/semantic_migration_summary.json" \
  --manifest-output "$IDEM_SEM/semantic_migration_manifest.json"
cmp "$FREDDIE_SEMANTIC_V3_DIR/claims_final.jsonl" "$IDEM_SEM/claims_final.jsonl"
cmp "$FREDDIE_SEMANTIC_V3_DIR/semantic_migration_changes.jsonl" "$IDEM_SEM/semantic_migration_changes.jsonl"

python3 "$ROOT/scripts/research/freddie_m19_acceptance_0017.py" \
  --generation-index "$FREDDIE_GENERATION_INDEX" \
  --effective-extraction "$FREDDIE_EFFECTIVE_EXTRACTION_DIR/claims.jsonl" \
  --replay-dir "$FREDDIE_REPLAY_V2_DIR" \
  --semantic-dir "$FREDDIE_SEMANTIC_V3_DIR"
