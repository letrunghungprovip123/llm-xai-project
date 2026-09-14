#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(git rev-parse --show-toplevel)}"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
unset DEEPSEEK_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY || true
bash "$ROOT/scripts/research/run_multidataset_m29a_visualization_input_lock_0036.sh" "$ROOT"
bash "$ROOT/scripts/research/run_multidataset_m29b_visualization_0037.sh" "$ROOT"
bash "$ROOT/scripts/research/run_multidataset_m30a_dashboard_foundation_0038.sh" "$ROOT"
bash "$ROOT/scripts/research/run_multidataset_m30b_overview_0039.sh" "$ROOT"
echo "MULTIDATASET_M29_M30_0036_0039=PASS"
