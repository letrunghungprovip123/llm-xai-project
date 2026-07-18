#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf '[batch-i] %s\n' "$*"
}

die() {
  printf '[batch-i] ERROR: %s\n' "$*" >&2
  exit 2
}

require_env() {
  local name="$1"
  [[ -n "${!name:-}" ]] || die "Missing env: ${name}"
}

cleanup() {
  local exit_code=$?

  # Ngăn cleanup bị gọi lặp lại bởi lệnh exit bên dưới.
  trap - EXIT INT TERM

  echo "[AUDIT] {\"event\":\"container_cleanup\",\"exit_code\":${exit_code},\"utc\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"

  if [[ -n "${GPU_MONITOR_PID:-}" ]] \
      && kill -0 "${GPU_MONITOR_PID}" 2>/dev/null; then
    log "Stopping GPU monitor process ${GPU_MONITOR_PID}"
    kill "${GPU_MONITOR_PID}" 2>/dev/null || true
    wait "${GPU_MONITOR_PID}" 2>/dev/null || true
  fi

  if [[ -n "${VLLM_PID:-}" ]] \
      && kill -0 "${VLLM_PID}" 2>/dev/null; then
    log "Stopping vLLM process ${VLLM_PID}"
    kill "${VLLM_PID}" 2>/dev/null || true
    wait "${VLLM_PID}" 2>/dev/null || true
  fi

  exit "${exit_code}"
}

trap cleanup EXIT INT TERM

for name in RUN_ID MODEL_ID HF_MODEL_ID INPUT_URI OUTPUT_URI; do
  require_env "${name}"
done

REPEAT_ID="${REPEAT_ID:-1}"
EXPERIMENT_STAGE="${EXPERIMENT_STAGE:-evaluation}"
EVIDENCE_LEVELS="${EVIDENCE_LEVELS:-S0,S1,S2,S3,S4,S5}"
CHECKPOINT_EVERY="${CHECKPOINT_EVERY:-10}"
CONCURRENCY="${CONCURRENCY:-1}"
PROMPT_VERSION="${PROMPT_VERSION:-prompt_v1}"
OUTPUT_SCHEMA_VERSION="${OUTPUT_SCHEMA_VERSION:-1.0}"
MAX_TOKENS="${MAX_TOKENS:-2000}"

VLLM_HOST="${VLLM_HOST:-127.0.0.1}"
VLLM_PORT="${VLLM_PORT:-8000}"
VLLM_DTYPE="${VLLM_DTYPE:-auto}"
VLLM_MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-12288}"
VLLM_GPU_MEMORY_UTILIZATION="${VLLM_GPU_MEMORY_UTILIZATION:-0.90}"
VLLM_STARTUP_TIMEOUT_SECONDS="${VLLM_STARTUP_TIMEOUT_SECONDS:-1800}"

SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-$HF_MODEL_ID}"
SOURCE_REVISION="${SOURCE_REVISION:-unknown}"

export VLLM_BASE_URL="http://${VLLM_HOST}:${VLLM_PORT}/v1"

log "revision=${SOURCE_REVISION}"
log "run=${RUN_ID} model=${MODEL_ID} hf_model=${HF_MODEL_ID}"

nvidia-smi || die "NVIDIA GPU is unavailable"

log "Collecting runtime metadata"
/usr/local/bin/batch-i-runtime-metadata

log "Starting GPU telemetry"
/usr/local/bin/batch-i-gpu-monitor &
GPU_MONITOR_PID=$!

echo "[AUDIT] {\"event\":\"vllm_starting\",\"utc\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"model\":\"${HF_MODEL_ID}\"}"

ARGS=(
  --model "${HF_MODEL_ID}"
  --served-model-name "${SERVED_MODEL_NAME}"
  --host "${VLLM_HOST}"
  --port "${VLLM_PORT}"
  --dtype "${VLLM_DTYPE}"
  --max-model-len "${VLLM_MAX_MODEL_LEN}"
  --gpu-memory-utilization "${VLLM_GPU_MEMORY_UTILIZATION}"
  --no-enable-log-requests
)

[[ -n "${MODEL_REVISION:-}" ]] \
  && ARGS+=(--revision "${MODEL_REVISION}")

if [[ -n "${VLLM_EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  EXTRA=( ${VLLM_EXTRA_ARGS} )
  ARGS+=("${EXTRA[@]}")
fi

python3 -m vllm.entrypoints.openai.api_server "${ARGS[@]}" &
VLLM_PID=$!

started="$(date +%s)"

until python3 - "${VLLM_HOST}" "${VLLM_PORT}" <<'PY'
import sys
import urllib.request

try:
    with urllib.request.urlopen(
        f"http://{sys.argv[1]}:{sys.argv[2]}/health",
        timeout=3,
    ) as response:
        raise SystemExit(0 if 200 <= response.status < 300 else 1)
except Exception:
    raise SystemExit(1)
PY
do
  kill -0 "${VLLM_PID}" 2>/dev/null \
    || die "vLLM exited before health check passed"

  (( $(date +%s) - started < VLLM_STARTUP_TIMEOUT_SECONDS )) \
    || die "vLLM startup timed out"

  sleep 5
done

echo "[AUDIT] {\"event\":\"vllm_ready\",\"utc\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"model\":\"${HF_MODEL_ID}\"}"

RUN_ARGS=(
  --input "${INPUT_URI}"
  --output-dir "${OUTPUT_URI}"
  --run-id "${RUN_ID}"
  --models "${MODEL_ID}"
  --levels "${EVIDENCE_LEVELS}"
  --repeat "${REPEAT_ID}"
  --checkpoint-every "${CHECKPOINT_EVERY}"
  --concurrency "${CONCURRENCY}"
  --prompt-version "${PROMPT_VERSION}"
  --output-schema-version "${OUTPUT_SCHEMA_VERSION}"
  --max-tokens "${MAX_TOKENS}"
  --experiment-stage "${EXPERIMENT_STAGE}"
  --resume
)

[[ -n "${LIMIT_CASES:-}" ]] \
  && RUN_ARGS+=(--limit "${LIMIT_CASES}")

[[ -n "${CHUNK_START:-}" ]] \
  && RUN_ARGS+=(--chunk-start "${CHUNK_START}")

[[ -n "${CHUNK_SIZE:-}" ]] \
  && RUN_ARGS+=(--chunk-size "${CHUNK_SIZE}")

echo "[AUDIT] {\"event\":\"batch_worker_starting\",\"utc\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"run_id\":\"${RUN_ID}\"}"

npm run batch:i -- "${RUN_ARGS[@]}"

echo "[AUDIT] {\"event\":\"batch_worker_completed\",\"utc\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"run_id\":\"${RUN_ID}\"}"

log "completed"
