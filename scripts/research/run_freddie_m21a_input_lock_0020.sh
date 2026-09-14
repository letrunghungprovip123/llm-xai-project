#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m21_m23_common_0020.sh"
freddie_analysis_paths "$ROOT"
freddie_assert_no_provider_execution
for file in \
  "$FREDDIE_ANALYSIS_PROTOCOL" \
  "$FREDDIE_GENERATION_INDEX" \
  "$FREDDIE_EVIDENCE_PACKAGES" \
  "$FREDDIE_CLAIMS_V3" \
  "$FREDDIE_VALIDATION_RESULTS" \
  "$FREDDIE_GENERATION_SUMMARIES" \
  "$FREDDIE_VALIDATION_MANIFEST" \
  "$FREDDIE_M20_INPUT_LOCK"
do
  freddie_require_file "$file"
done
mkdir -p "$FREDDIE_ANALYSIS_INPUT_LOCK_DIR"
python3 "$ROOT/scripts/research/freddie_analysis_input_lock_0020.py" \
  --repo-root "$ROOT" \
  --protocol "$FREDDIE_ANALYSIS_PROTOCOL" \
  --generation-index "$FREDDIE_GENERATION_INDEX" \
  --evidence-packages "$FREDDIE_EVIDENCE_PACKAGES" \
  --claims "$FREDDIE_CLAIMS_V3" \
  --validation-results "$FREDDIE_VALIDATION_RESULTS" \
  --generation-summaries "$FREDDIE_GENERATION_SUMMARIES" \
  --validation-manifest "$FREDDIE_VALIDATION_MANIFEST" \
  --m20-input-lock "$FREDDIE_M20_INPUT_LOCK" \
  --output "$FREDDIE_ANALYSIS_INPUT_LOCK"
