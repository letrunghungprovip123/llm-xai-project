#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
: "${AWS_REGION:?Set AWS_REGION}"
: "${AWS_ACCOUNT_ID:?Set AWS_ACCOUNT_ID}"
REPO="${ECR_REPOSITORY:-llm-xai-batch-i}"
SHA="${GIT_SHA:-$(git rev-parse --short=12 HEAD)}"
LOCAL="${LOCAL_IMAGE:-llm-xai-batch-i:$SHA}"
HOST="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
REMOTE="$HOST/$REPO:$SHA"

aws ecr describe-repositories --region "$AWS_REGION" --repository-names "$REPO" >/dev/null 2>&1 ||
aws ecr create-repository --region "$AWS_REGION" --repository-name "$REPO" \
  --image-scanning-configuration scanOnPush=true >/dev/null

aws ecr get-login-password --region "$AWS_REGION" |
docker login --username AWS --password-stdin "$HOST"

docker tag "$LOCAL" "$REMOTE"
docker push "$REMOTE"

DIGEST=$(aws ecr describe-images --region "$AWS_REGION" --repository-name "$REPO" \
  --image-ids "imageTag=$SHA" --query 'imageDetails[0].imageDigest' --output text)
echo "Image: $REMOTE"
echo "Immutable: $HOST/$REPO@$DIGEST"
