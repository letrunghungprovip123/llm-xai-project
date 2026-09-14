#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/multidataset_m27_m28_common_0032.sh"
multidataset_m27_m28_paths "$ROOT"
m24_m26_assert_no_provider_execution
mkdir -p "$MULTIDATASET_M27_LOCK_DIR"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
unset DEEPSEEK_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY || true
python3 "$ROOT/scripts/research/multidataset_m27_robustness_input_lock_0032.py" \
  --repo-root "$ROOT" --protocol "$MULTIDATASET_M27_PROTOCOL" \
  --m25-lock "$MULTIDATASET_M25_LOCK" --m25-dir "$MULTIDATASET_M25_DIR" \
  --m26-policy-lock "$MULTIDATASET_M26_POLICY_LOCK" --m26-dir "$MULTIDATASET_M26_DIR" \
  --output "$MULTIDATASET_M27_LOCK"
