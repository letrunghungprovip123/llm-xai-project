#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/multidataset_m27_m28_common_0032.sh"
multidataset_m27_m28_paths "$ROOT"
m24_m26_assert_no_provider_execution
mkdir -p "$MULTIDATASET_M28_LOCK_DIR"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
unset DEEPSEEK_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY || true
python3 "$ROOT/scripts/research/multidataset_m28_analytical_release_input_lock_0034.py" --repo-root "$ROOT" --protocol "$MULTIDATASET_M28_PROTOCOL" --m27-lock "$MULTIDATASET_M27_LOCK" --m27-dir "$MULTIDATASET_M27_DIR" --output "$MULTIDATASET_M28_LOCK"
