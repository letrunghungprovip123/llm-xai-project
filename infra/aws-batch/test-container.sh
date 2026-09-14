#!/usr/bin/env bash
set -Eeuo pipefail
IMAGE="${1:-llm-xai-batch-i:5cd405fec7aa}"
docker run --rm --platform linux/amd64 --entrypoint /bin/bash "$IMAGE" \
  -lc 'node --version && npm --version && npm run typecheck:batch-i'
