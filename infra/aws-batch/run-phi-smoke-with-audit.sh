#!/usr/bin/env bash
set -Eeuo pipefail
export AWS_PAGER=""



EVIDENCE_LEVELS="${EVIDENCE_LEVELS:-S0,S4,S5}"
LIMIT_CASES="${LIMIT_CASES:-1}"
MAX_TOKENS="${MAX_TOKENS:-2000}"
REPEAT_ID="${REPEAT_ID:-1}"
EXPERIMENT_STAGE="${EXPERIMENT_STAGE:-development}"
CHECKPOINT_EVERY="${CHECKPOINT_EVERY:-10}"
CONCURRENCY="${CONCURRENCY:-1}"
REGION="${AWS_REGION:-us-east-1}"
BUCKET="${AUDIT_BUCKET:-llm-xai-batch-i-699475930862-us-east-1}"
JOB_QUEUE="${JOB_QUEUE:-llm-xai-gpu-ondemand-queue}"
COMPUTE_ENVIRONMENT="${COMPUTE_ENVIRONMENT:-llm-xai-gpu-ondemand-ce}"
JOB_DEFINITION="${JOB_DEFINITION:-llm-xai-batch-i-gpu-smoke:2}"

RUN_ID="${RUN_ID:-run_phi4_mini_smoke_001}"
MODEL_ID="${MODEL_ID:-phi4_mini_instruct}"
HF_MODEL_ID="${HF_MODEL_ID:-microsoft/Phi-4-mini-instruct}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-microsoft/Phi-4-mini-instruct}"

INPUT_URI="${INPUT_URI:-s3://${BUCKET}/batch-i/inputs/evaluation_36/evidence_packages_36.jsonl}"
OUTPUT_URI="${OUTPUT_URI:-s3://${BUCKET}/batch-i/runs/${RUN_ID}/outputs}"
AUDIT_DIR="${AUDIT_DIR:-data/reports/batch_i_execution/${RUN_ID}}"
LOG_GROUP="${LOG_GROUP:-/aws/batch/llm-xai-batch-i}"

mkdir -p "${AUDIT_DIR}"

log(){ printf '[submit-smoke] %s\n' "$*"; }
die(){ printf '[submit-smoke] ERROR: %s\n' "$*" >&2; exit 2; }

QUEUE_STATE=$(aws batch describe-job-queues --region "$REGION" --job-queues "$JOB_QUEUE" --query 'jobQueues[0].state' --output text)
QUEUE_STATUS=$(aws batch describe-job-queues --region "$REGION" --job-queues "$JOB_QUEUE" --query 'jobQueues[0].status' --output text)
[[ "$QUEUE_STATE" == "ENABLED" ]] || die "Queue state=$QUEUE_STATE"
[[ "$QUEUE_STATUS" == "VALID" ]] || die "Queue status=$QUEUE_STATUS"

CE_STATE=$(aws batch describe-compute-environments --region "$REGION" --compute-environments "$COMPUTE_ENVIRONMENT" --query 'computeEnvironments[0].state' --output text)
CE_STATUS=$(aws batch describe-compute-environments --region "$REGION" --compute-environments "$COMPUTE_ENVIRONMENT" --query 'computeEnvironments[0].status' --output text)
[[ "$CE_STATE" == "ENABLED" ]] || die "Compute environment state=$CE_STATE"
[[ "$CE_STATUS" == "VALID" ]] || die "Compute environment status=$CE_STATUS"

aws s3api head-object --region "$REGION" --bucket "$BUCKET" --key "batch-i/inputs/evaluation_36/evidence_packages_36.jsonl" > "$AUDIT_DIR/input-head-object.json"

cat > "$AUDIT_DIR/run-manifest.json" <<EOF
{
  "run_id": "$RUN_ID",
  "experiment_stage": "development",
  "model_id": "$MODEL_ID",
  "hf_model_id": "$HF_MODEL_ID",
  "job_definition": "$JOB_DEFINITION",
  "job_queue": "$JOB_QUEUE",
  "compute_environment": "$COMPUTE_ENVIRONMENT",
  "region": "$REGION",
  "input_uri": "$INPUT_URI",
  "output_uri": "$OUTPUT_URI",
  "resource_request": {"vcpu": 8, "memory_mib": 28672, "gpu": 1},
  "levels": ["S0", "S4", "S5"],
  "limit_cases": 1,
  "max_tokens": 2000,
  "repeat": 1
}
EOF

cat > "$AUDIT_DIR/submit-request.json" <<EOF
{
  "jobName": "$RUN_ID",
  "jobQueue": "$JOB_QUEUE",
  "jobDefinition": "$JOB_DEFINITION",
  "containerOverrides": {
    "environment": [
      {"name": "RUN_ID", "value": "$RUN_ID"},
      {"name": "MODEL_ID", "value": "$MODEL_ID"},
      {"name": "HF_MODEL_ID", "value": "$HF_MODEL_ID"},
      {"name": "SERVED_MODEL_NAME", "value": "$SERVED_MODEL_NAME"},
      {"name": "INPUT_URI", "value": "$INPUT_URI"},
      {"name": "OUTPUT_URI", "value": "$OUTPUT_URI"}
    ]
  },
  "tags": {
    "Project": "llm-xai-batch-i",
    "RunId": "$RUN_ID",
    "Model": "phi4-mini",
    "Stage": "smoke"
  },
  "propagateTags": true
}
EOF

log "Submitting $RUN_ID"
aws batch submit-job --region "$REGION" --cli-input-json "file://$AUDIT_DIR/submit-request.json" | tee "$AUDIT_DIR/submission.json"

JOB_ID=$(python3 -c 'import json; print(json.load(open("'"$AUDIT_DIR"'/submission.json"))["jobId"])')
echo "$JOB_ID" > "$AUDIT_DIR/job-id.txt"
log "Job ID: $JOB_ID"

LAST_STATUS=""
while true; do
  aws batch describe-jobs --region "$REGION" --jobs "$JOB_ID" > "$AUDIT_DIR/batch-job-current.json"
  STATUS=$(python3 -c 'import json; print(json.load(open("'"$AUDIT_DIR"'/batch-job-current.json"))["jobs"][0]["status"])')
  if [[ "$STATUS" != "$LAST_STATUS" ]]; then
    printf '%s,%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$STATUS" | tee -a "$AUDIT_DIR/status-timeline.csv"
    LAST_STATUS="$STATUS"
  fi
  [[ "$STATUS" == "SUCCEEDED" || "$STATUS" == "FAILED" ]] && break
  sleep 20
done

cp "$AUDIT_DIR/batch-job-current.json" "$AUDIT_DIR/batch-job-final.json"

python3 - "$AUDIT_DIR/batch-job-final.json" > "$AUDIT_DIR/execution-summary.json" <<'PY'
import json, sys
job = json.load(open(sys.argv[1]))["jobs"][0]
created, started, stopped = job.get("createdAt"), job.get("startedAt"), job.get("stoppedAt")
summary = {
    "job_id": job.get("jobId"),
    "status": job.get("status"),
    "status_reason": job.get("statusReason"),
    "created_at_ms": created,
    "started_at_ms": started,
    "stopped_at_ms": stopped,
    "queue_wait_ms": started-created if created and started else None,
    "execution_ms": stopped-started if started and stopped else None,
    "total_elapsed_ms": stopped-created if created and stopped else None,
    "attempt_count": len(job.get("attempts", [])),
    "exit_code": job.get("container", {}).get("exitCode"),
    "container_reason": job.get("container", {}).get("reason"),
    "log_stream_name": job.get("container", {}).get("logStreamName"),
    "job_definition": job.get("jobDefinition"),
    "resource_requirements": job.get("container", {}).get("resourceRequirements", [])
}
print(json.dumps(summary, indent=2))
PY

LOG_STREAM=$(python3 -c 'import json; j=json.load(open("'"$AUDIT_DIR"'/batch-job-final.json"))["jobs"][0]; print(j.get("container",{}).get("logStreamName",""))')

if [[ -n "$LOG_STREAM" ]]; then
  aws logs get-log-events --region "$REGION" --log-group-name "$LOG_GROUP" --log-stream-name "$LOG_STREAM" --start-from-head --output json > "$AUDIT_DIR/cloudwatch-events.json"
  python3 - "$AUDIT_DIR/cloudwatch-events.json" > "$AUDIT_DIR/cloudwatch.log" <<'PY'
import json, sys
from datetime import datetime, timezone
for event in json.load(open(sys.argv[1])).get("events", []):
    ts = datetime.fromtimestamp(event["timestamp"]/1000, tz=timezone.utc).isoformat()
    print(f"{ts} {event['message']}")
PY
fi

aws s3 sync "$AUDIT_DIR" "s3://$BUCKET/batch-i/runs/$RUN_ID/audit/"

FINAL_STATUS=$(python3 -c 'import json; print(json.load(open("'"$AUDIT_DIR"'/execution-summary.json"))["status"])')
log "Final status: $FINAL_STATUS"
log "Audit local: $AUDIT_DIR"
log "Audit S3: s3://$BUCKET/batch-i/runs/$RUN_ID/audit/"

[[ "$FINAL_STATUS" == "SUCCEEDED" ]]
