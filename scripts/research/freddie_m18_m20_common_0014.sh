#!/usr/bin/env bash
set -euo pipefail

freddie_repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || {
    echo "ERROR: run this script inside the llm-xai-next-refactor Git repository." >&2
    return 2
  }
}

freddie_config_path() {
  local root="$1"
  printf '%s\n' "$root/config/research/replication/freddie_sflld_2024_downstream_v1.json"
}

freddie_config_value() {
  local root="$1" key="$2"
  python3 - "$root" "$key" <<'PYCFG'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
key = sys.argv[2]
config = json.loads((root / "config/research/replication/freddie_sflld_2024_downstream_v1.json").read_text())
value = config
for part in key.split('.'):
    value = value[part]
if isinstance(value, (dict, list)):
    print(json.dumps(value, separators=(",", ":")))
else:
    print(value)
PYCFG
}

freddie_paths() {
  local root="$1"
  FREDDIE_CANONICAL_DIR="$root/$(freddie_config_value "$root" canonical_output_dir)"
  FREDDIE_CLAIM_ROOT="$root/$(freddie_config_value "$root" claim_root)"
  FREDDIE_FINALIZATION_ROOT="$root/$(freddie_config_value "$root" finalization_root)"
  FREDDIE_VALIDATION_ROOT="${FREDDIE_FINALIZATION_ROOT%/claim_finalization}/claim_validation"
  FREDDIE_GENERATION_INDEX="$FREDDIE_CANONICAL_DIR/generation_index.jsonl"
  FREDDIE_EVIDENCE_PACKAGES="$FREDDIE_CANONICAL_DIR/evidence_packages_36.jsonl"
  FREDDIE_HISTORICAL_CLAIMS="$FREDDIE_CLAIM_ROOT/full/claims.jsonl"
  FREDDIE_HISTORICAL_ATTEMPTS="$FREDDIE_CLAIM_ROOT/full/claim_extraction_attempts.jsonl"
  FREDDIE_HISTORICAL_FAILURES="$FREDDIE_CLAIM_ROOT/full/claim_extraction_failures.jsonl"
  FREDDIE_OFFLINE_FREEZE_DIR="$FREDDIE_CLAIM_ROOT/offline_response_freeze_v1"
  FREDDIE_EFFECTIVE_EXTRACTION_DIR="$FREDDIE_CLAIM_ROOT/effective_offline_v1"
  FREDDIE_M19_PREFLIGHT_DIR="$FREDDIE_FINALIZATION_ROOT/offline_v1/preflight"
  FREDDIE_REPLAY_V2_DIR="$FREDDIE_FINALIZATION_ROOT/offline_v1/replay_v2"
  FREDDIE_SEMANTIC_V3_DIR="$FREDDIE_FINALIZATION_ROOT/offline_v1/semantic_v3"
  FREDDIE_VALIDATION_LOCK_DIR="$FREDDIE_VALIDATION_ROOT/input_lock_v1"
  FREDDIE_VALIDATION_OUT_DIR="$FREDDIE_VALIDATION_ROOT/deterministic_v4"
}

freddie_require_file() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "ERROR: required file is missing: $file" >&2
    exit 2
  fi
}

freddie_sha256() {
  shasum -a 256 "$1" | awk '{print $1}'
}

freddie_assert_no_provider_execution() {
  # Downstream stages are deterministic. Remove provider credentials from the
  # child environment so an accidental provider path cannot authenticate.
  unset DEEPSEEK_API_KEY OPENAI_API_KEY AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN || true
}
