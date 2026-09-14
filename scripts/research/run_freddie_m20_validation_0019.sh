#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m18_m20_common_0014.sh"
freddie_paths "$ROOT"
freddie_assert_no_provider_execution
LOCK="$FREDDIE_VALIDATION_LOCK_DIR/freddie_validation_input_lock.json"
freddie_require_file "$LOCK"

# Reverify every locked input before validation. Do not create output on drift.
python3 - "$ROOT" "$LOCK" <<'PYLOCK'
import hashlib, json, pathlib, sys
root=pathlib.Path(sys.argv[1])
lock=json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
for name,d in lock["artifacts"].items():
    p=pathlib.Path(d["path"])
    p=p if p.is_absolute() else root/p
    if not p.is_file():
        raise SystemExit(f"INPUT LOCK MISSING — STOP: {name}: {p}")
    actual=hashlib.sha256(p.read_bytes()).hexdigest()
    if actual != d["sha256"]:
        raise SystemExit(f"INPUT LOCK DRIFT — STOP: {name}: expected={d['sha256']} actual={actual}")
print("FREDDIE_M20_INPUT_LOCK_REVERIFY=PASS")
PYLOCK

CLAIMS="$FREDDIE_SEMANTIC_V3_DIR/claims_final.jsonl"
mkdir -p "$(dirname "$FREDDIE_VALIDATION_OUT_DIR")"
if [[ -e "$FREDDIE_VALIDATION_OUT_DIR" ]]; then
  echo "ERROR: validation output already exists; refusing to overwrite: $FREDDIE_VALIDATION_OUT_DIR" >&2
  exit 4
fi

npm run research -- llm:validate -- \
  --claims-input "$CLAIMS" \
  --generation-index "$FREDDIE_GENERATION_INDEX" \
  --evidence-packages "$FREDDIE_EVIDENCE_PACKAGES" \
  --output-dir "$FREDDIE_VALIDATION_OUT_DIR" \
  --mode deterministic \
  --smoke false \
  --force false

python3 "$ROOT/scripts/research/freddie_m20_acceptance_0019.py" \
  --lock "$LOCK" \
  --repo-root "$ROOT" \
  --output-dir "$FREDDIE_VALIDATION_OUT_DIR"
