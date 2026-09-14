#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
GIT_SHA="${GIT_SHA:-$(git rev-parse --short=12 HEAD)}"
IMAGE_NAME="${IMAGE_NAME:-llm-xai-batch-i}"
VLLM_IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:v0.21.0}"
docker buildx build \
  --platform linux/amd64 \
  --build-arg "VLLM_IMAGE=$VLLM_IMAGE" \
  -f infra/aws-batch/Dockerfile \
  -t "$IMAGE_NAME:$GIT_SHA" \
  --load .
echo "Built $IMAGE_NAME:$GIT_SHA"
