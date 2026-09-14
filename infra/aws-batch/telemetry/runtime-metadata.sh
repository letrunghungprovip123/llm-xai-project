#!/usr/bin/env bash
set -Eeuo pipefail

echo '[AUDIT] {"event":"runtime_metadata_started"}'

echo "[RUNTIME] utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[RUNTIME] hostname=$(hostname)"
echo "[RUNTIME] kernel=$(uname -srmo)"
echo "[RUNTIME] architecture=$(uname -m)"
echo "[RUNTIME] node=$(node --version 2>/dev/null || true)"
echo "[RUNTIME] npm=$(npm --version 2>/dev/null || true)"
echo "[RUNTIME] python=$(python3 --version 2>/dev/null || true)"
echo "[RUNTIME] git_revision=${SOURCE_REVISION:-unknown}"
echo "[RUNTIME] image_digest=${IMAGE_DIGEST:-unknown}"
echo "[RUNTIME] aws_batch_job_id=${AWS_BATCH_JOB_ID:-unknown}"
echo "[RUNTIME] aws_batch_job_name=${AWS_BATCH_JOB_NAME:-unknown}"
echo "[RUNTIME] aws_batch_job_attempt=${AWS_BATCH_JOB_ATTEMPT:-unknown}"
echo "[RUNTIME] aws_region=${AWS_REGION:-unknown}"

echo '[GPU_STATIC_BEGIN]'
nvidia-smi -q || true
echo '[GPU_STATIC_END]'

if [[ -n "${ECS_CONTAINER_METADATA_URI_V4:-}" ]]; then
  echo '[ECS_CONTAINER_METADATA_BEGIN]'

  python3 - <<'PY'
import json
import os
import urllib.request

base = os.environ.get("ECS_CONTAINER_METADATA_URI_V4")

for suffix in ("", "/task"):
    try:
        with urllib.request.urlopen(base + suffix, timeout=5) as response:
            data = json.load(response)

        print(json.dumps({
            "endpoint": suffix or "/",
            "metadata": data,
        }, separators=(",", ":"), default=str))
    except Exception as error:
        print(json.dumps({
            "endpoint": suffix or "/",
            "error": str(error),
        }))
PY

  echo '[ECS_CONTAINER_METADATA_END]'
else
  echo '[RUNTIME] ecs_metadata_uri=unavailable'
fi

echo '[AUDIT] {"event":"runtime_metadata_completed"}'
