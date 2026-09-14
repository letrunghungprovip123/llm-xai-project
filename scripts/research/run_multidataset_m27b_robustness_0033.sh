#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/multidataset_m27_m28_common_0032.sh"
multidataset_m27_m28_paths "$ROOT"
m24_m26_assert_no_provider_execution
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
unset DEEPSEEK_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY || true
python3 "$ROOT/scripts/research/multidataset_m27_robustness_0033.py" --repo-root "$ROOT" --input-lock "$MULTIDATASET_M27_LOCK" --output-dir "$MULTIDATASET_M27_DIR"
