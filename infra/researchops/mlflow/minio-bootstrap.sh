#!/bin/sh
set -eu

: "${RESEARCHOPS_S3_ACCESS_KEY:?}"
: "${RESEARCHOPS_S3_SECRET_KEY:?}"
: "${MLFLOW_S3_BUCKET:?}"
: "${MLFLOW_S3_ACCESS_KEY:?}"
: "${MLFLOW_S3_SECRET_KEY:?}"
: "${MINIO_ENDPOINT:=http://researchops-minio:9000}"

case "$MLFLOW_S3_BUCKET" in
  *[!a-z0-9.-]*|'') echo "Invalid MLFLOW_S3_BUCKET" >&2; exit 2 ;;
esac

mc alias set local "$MINIO_ENDPOINT" \
  "$RESEARCHOPS_S3_ACCESS_KEY" "$RESEARCHOPS_S3_SECRET_KEY" >/dev/null
mc ready local >/dev/null
mc mb --ignore-existing "local/${MLFLOW_S3_BUCKET}" >/dev/null
mc version enable "local/${MLFLOW_S3_BUCKET}" >/dev/null

POLICY_NAME="researchops-mlflow-${MLFLOW_S3_BUCKET}"
POLICY_FILE="/tmp/mlflow-policy.json"
cat > "$POLICY_FILE" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::${MLFLOW_S3_BUCKET}"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::${MLFLOW_S3_BUCKET}/*"]
    }
  ]
}
JSON

# `policy create` overwrites an existing policy, so reruns repair policy drift.
mc admin policy create local "$POLICY_NAME" "$POLICY_FILE" >/dev/null
# Adding an existing user updates its secret, keeping reruns and secret rotation safe.
mc admin user add local "$MLFLOW_S3_ACCESS_KEY" "$MLFLOW_S3_SECRET_KEY" >/dev/null
mc admin user enable local "$MLFLOW_S3_ACCESS_KEY" >/dev/null
mc admin policy attach local "$POLICY_NAME" \
  --user "$MLFLOW_S3_ACCESS_KEY" >/dev/null

PROBE="mlflow-bootstrap-$(date +%s)-$$"
printf '%s\n' "$PROBE" | mc pipe "local/${MLFLOW_S3_BUCKET}/.bootstrap/${PROBE}.txt" >/dev/null
OBSERVED="$(mc cat "local/${MLFLOW_S3_BUCKET}/.bootstrap/${PROBE}.txt")"
[ "$OBSERVED" = "$PROBE" ]
mc rm "local/${MLFLOW_S3_BUCKET}/.bootstrap/${PROBE}.txt" >/dev/null

echo "MLFLOW_MINIO_BOOTSTRAP=PASS"
