#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/multidataset_m27_m28_common_0032.sh"
multidataset_m27_m28_paths "$ROOT"
m24_m26_assert_no_provider_execution
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
unset DEEPSEEK_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY || true
python3 "$ROOT/scripts/research/multidataset_m28_analytical_release_0035.py" --repo-root "$ROOT" --input-lock "$MULTIDATASET_M28_LOCK" --output-dir "$MULTIDATASET_M28_DIR"
