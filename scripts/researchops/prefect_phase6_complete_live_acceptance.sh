#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"

PYTHON="${RESEARCHOPS_PYTHON:-$ROOT/.venv/bin/python3}"
PREFECT_CLI="${RESEARCHOPS_PREFECT_CLI:-$ROOT/.venv/bin/prefect}"
REPORT_ROOT="${RESEARCHOPS_PREFECT_PHASE6_LIVE_DIR:-/tmp/researchops-prefect-phase6-live}"
APPROVAL_RESUME_TIMEOUT="${RESEARCHOPS_PREFECT_APPROVAL_RESUME_TIMEOUT:-30}"
APPROVAL_RESUME_POLL_INTERVAL="${RESEARCHOPS_PREFECT_APPROVAL_RESUME_POLL_INTERVAL:-0.5}"
DB_ENV=.env.researchops-db.local
PREFECT_ENV=.env.researchops-prefect.local

SESSION_ID="${RESEARCHOPS_PHASE6_ACCEPTANCE_SESSION_ID:-}"
if [[ -z "$SESSION_ID" ]]; then
  SESSION_ID="phase6-$(date -u +%Y%m%d-%H%M%S)-$("$PYTHON" - <<'PY'
from uuid import uuid4
print(uuid4().hex[:10])
PY
)"
fi
if [[ ! "$SESSION_ID" =~ ^[a-z0-9-]+$ ]]; then
  echo "ERROR: RESEARCHOPS_PHASE6_ACCEPTANCE_SESSION_ID must match ^[a-z0-9-]+$" >&2
  exit 2
fi

REPORT_DIR="$REPORT_ROOT/$SESSION_ID"
mkdir -p "$REPORT_DIR"
ln -sfn "$REPORT_DIR" "$REPORT_ROOT/latest"
CURRENT_STEP="initialization"
APPROVE_FLOW_ID=""
REJECT_FLOW_ID=""
CANCEL_ID=""
NORMAL_1_ID=""
NORMAL_2_ID=""

failure_report() {
  local status="$1" line="$2" command="$3"
  set +e
  FAILURE_COMMAND="$command" "$PYTHON" - \
    "$REPORT_DIR/failure.json" "$SESSION_ID" "$CURRENT_STEP" "$status" "$line" \
    "$APPROVE_FLOW_ID" "$REJECT_FLOW_ID" "$CANCEL_ID" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    output,
    session_id,
    step,
    exit_code,
    line,
    approve_flow_run_id,
    reject_flow_run_id,
    cancel_flow_run_id,
) = sys.argv[1:]
report = {
    "schema_version": "phase6_live_failure_v1",
    "passed": False,
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "session_id": session_id,
    "step": step,
    "exit_code": int(exit_code),
    "line": int(line),
    "command": os.environ.get("FAILURE_COMMAND", ""),
    "flow_run_ids": {
        "approval": approve_flow_run_id or None,
        "rejection": reject_flow_run_id or None,
        "cancellation": cancel_flow_run_id or None,
    },
}
Path(output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
PY
  echo "PHASE6_LIVE_FAILURE_REPORT=$REPORT_DIR/failure.json" >&2
  exit "$status"
}
trap 'failure_report "$?" "$LINENO" "$BASH_COMMAND"' ERR

[[ -x "$PYTHON" ]] || { echo "ERROR: missing Python: $PYTHON" >&2; exit 2; }
[[ -x "$PREFECT_CLI" ]] || { echo "ERROR: missing Prefect CLI: $PREFECT_CLI" >&2; exit 2; }
[[ -f "$DB_ENV" ]] || { echo "ERROR: missing $DB_ENV" >&2; exit 2; }
[[ -f "$PREFECT_ENV" ]] || { echo "ERROR: missing $PREFECT_ENV" >&2; exit 2; }
for file in "$DB_ENV" "$PREFECT_ENV" .env.researchops-storage.local .env.researchops-mlflow.local; do
  if [[ -f "$file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$file"
    set +a
  fi
done

[[ -n "${RESEARCHOPS_PHASE5_SOURCE_ARTIFACT_ID:-}" ]] || {
  echo "ERROR: set RESEARCHOPS_PHASE5_SOURCE_ARTIFACT_ID for the accepted trained-model artifact" >&2
  exit 2
}

make_parameters() {
  local kind="$1" simulation="$2" sleep_seconds="$3" scenario="$4"
  "$PYTHON" - "$kind" "$simulation" "$sleep_seconds" "$scenario" "$SESSION_ID" <<'PY'
import json
import sys
kind, simulation, sleep_seconds, scenario, session_id = sys.argv[1:]
parameters = {
    "simulation": simulation,
    "sleep_seconds": int(sleep_seconds),
    "acceptance_session": session_id,
    "acceptance_scenario": scenario,
}
if kind == "standard":
    parameters["enable_acceptance_fixture"] = True
elif kind == "approval":
    parameters["enable_approval_acceptance"] = True
elif kind == "mlflow":
    parameters = {
        "enable_mlflow_registration": True,
        "acceptance_session": session_id,
        "acceptance_scenario": scenario,
    }
else:
    raise SystemExit(f"unsupported parameter kind: {kind}")
print(json.dumps({"parameters": parameters, "requested_by": f"phase6-live-{session_id}"}, separators=(",", ":")))
PY
}

run_report() {
  local name="$1" params="$2" timeout="$3" output="$4"
  "$PYTHON" -m research.python.researchops.orchestration.live_acceptance run \
    --deployment "$name" \
    --parameters-json "$params" \
    --timeout "$timeout" \
    --report-path "$output" >/dev/null
}

summary_report() {
  local flow_id="$1" output="$2"
  "$PYTHON" -m research.python.researchops.orchestration.live_acceptance ops-summary \
    --flow-run-id "$flow_id" --report-path "$output" >/dev/null
}

json_field() {
  "$PYTHON" - "$1" "$2" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for key in sys.argv[2].split("."):
    value = value[key]
print(value)
PY
}

wait_pending_approval() {
  local flow_run_id="$1" output="$2"
  rm -f "$output"
  for _attempt in $(seq 1 90); do
    if "$PYTHON" -m research.python.researchops.orchestration.live_acceptance \
        pending-approval --flow-run-id "$flow_run_id" --report-path "$output" \
        >/dev/null 2>&1; then
      [[ "$(json_field "$output" passed)" == True ]] && return 0
    fi
    sleep 2
  done
  echo "ERROR: pending approval was not published for flow run $flow_run_id" >&2
  return 1
}

wait_ops_running() {
  local flow_run_id="$1" output="$2"
  rm -f "$output"
  for _attempt in $(seq 1 120); do
    if summary_report "$flow_run_id" "$output" >/dev/null 2>&1; then
      if "$PYTHON" - "$output" <<'PY' >/dev/null 2>&1
import json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["passed"] is True
assert report["pipeline_status"] == "RUNNING"
assert report["stage_count"] > 0
assert any(item["status"] == "RUNNING" for item in report["stage_attempts"])
PY
      then
        return 0
      fi
    fi
    sleep 1
  done
  echo "ERROR: Ops pipeline/stage did not reach RUNNING for flow run $flow_run_id" >&2
  return 1
}

CURRENT_STEP="approval-key-contract-preflight"
"$PYTHON" - <<'PY'
from uuid import UUID
from prefect.client.schemas.objects import FlowRunInput
from prefect.input.run_input import keyset_from_base_key
from research.python.researchops.orchestration.approvals.service import approval_resume_key

resume_key = approval_resume_key("a" * 64)
assert resume_key == "approval-" + "a" * 64
for key in keyset_from_base_key(f"suspended-{resume_key}").values():
    FlowRunInput(
        flow_run_id=UUID("11111111-1111-1111-1111-111111111111"),
        key=key,
        value="{}",
    )
print("PREFECT_APPROVAL_RUN_INPUT_KEY_CONTRACT=PASS")
PY

CURRENT_STEP="legacy-stranded-run-report"
RESEARCHOPS_PREFECT_CLEANUP_DIR="$REPORT_DIR/stranded-cleanup" \
  scripts/researchops/prefect_phase6_cleanup_stranded_acceptance.sh

CURRENT_STEP="deployment-import-preflight"
"$PYTHON" -m research.python.researchops.orchestration.prefect_adapter.deployment_cli \
  import-check --report-path "$REPORT_DIR/deployment-imports.json"
echo "PREFECT_DEPLOYMENT_IMPORT_PREFLIGHT=PASS"

CURRENT_STEP="infrastructure-bootstrap"
"$PYTHON" -m alembic upgrade head
scripts/researchops/prefect_local.sh up

for _attempt in $(seq 1 120); do
  server="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' llm-xai-researchops-prefect-server 2>/dev/null || true)"
  worker="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' llm-xai-researchops-prefect-worker 2>/dev/null || true)"
  [[ "$server" == healthy && "$worker" == healthy ]] && break
  sleep 2
done
[[ "${server:-}" == healthy && "${worker:-}" == healthy ]] || {
  scripts/researchops/prefect_local.sh logs
  exit 1
}

docker cp \
  llm-xai-researchops-prefect-worker:/tmp/researchops-prefect-ops-database-preflight.json \
  "$REPORT_DIR/ops-database-preflight.json"
"$PYTHON" - "$REPORT_DIR/ops-database-preflight.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["passed"] is True, report
assert "***" in report["database_url"], report
print("PREFECT_OPS_DATABASE_CONNECTIVITY=PASS")
PY

CURRENT_STEP="deployment-bootstrap-idempotency"
docker compose --profile researchops-prefect run --rm researchops-prefect-deploy
docker compose --profile researchops-prefect run --rm researchops-prefect-deploy
echo "PREFECT_DEPLOYMENTS_BOOTSTRAP=PASS"
echo "PREFECT_DEPLOYMENTS_IDEMPOTENT=PASS"

CURRENT_STEP="approval-integration-smoke"
APPROVE_PARAMS="$(make_parameters approval normal 1 approval-approve)"
run_report 'prefect-approval-acceptance-fixture/local' "$APPROVE_PARAMS" 0 "$REPORT_DIR/approval-created.json"
APPROVE_FLOW_ID="$(json_field "$REPORT_DIR/approval-created.json" flow_run_id)"
wait_pending_approval "$APPROVE_FLOW_ID" "$REPORT_DIR/pending-approve.json"
APPROVAL_ID="$(json_field "$REPORT_DIR/pending-approve.json" approval_id)"
"$PYTHON" -m research.python.researchops.orchestration.approvals approve \
  --approval-id "$APPROVAL_ID" --actor phase6-reviewer \
  --reason 'Phase 6 live acceptance approval' --resume-prefect \
  --resume-timeout-seconds "$APPROVAL_RESUME_TIMEOUT" \
  --resume-poll-interval-seconds "$APPROVAL_RESUME_POLL_INTERVAL" \
  --report-path "$REPORT_DIR/approved.json" >/dev/null
[[ "$(json_field "$REPORT_DIR/approved.json" prefect_resumed)" == True ]]
"$PYTHON" -m research.python.researchops.orchestration.live_acceptance wait \
  --flow-run-id "$APPROVE_FLOW_ID" --timeout 600 \
  --report-path "$REPORT_DIR/approval-wait.json" >/dev/null
[[ "$(json_field "$REPORT_DIR/approval-wait.json" state_name)" == COMPLETED ]]
summary_report "$APPROVE_FLOW_ID" "$REPORT_DIR/approval-ops.json"
[[ "$(json_field "$REPORT_DIR/approval-ops.json" pipeline_status)" == SUCCEEDED ]]
echo "PREFECT_APPROVAL_INTEGRATION_SMOKE=PASS"
echo "PREFECT_APPROVAL_SUSPEND_RESUME=PASS"

CURRENT_STEP="flow-stage-receipt-idempotency"
NORMAL_PARAMS="$(make_parameters standard normal 0 normal-idempotency)"
run_report 'prefect-acceptance-fixture/local' "$NORMAL_PARAMS" 600 "$REPORT_DIR/normal-1.json"
[[ "$(json_field "$REPORT_DIR/normal-1.json" state_name)" == COMPLETED ]]
NORMAL_1_ID="$(json_field "$REPORT_DIR/normal-1.json" flow_run_id)"
summary_report "$NORMAL_1_ID" "$REPORT_DIR/normal-1-ops.json"
[[ "$(json_field "$REPORT_DIR/normal-1-ops.json" pipeline_status)" == SUCCEEDED ]]
[[ "$(json_field "$REPORT_DIR/normal-1-ops.json" receipt_artifact_id)" != None ]]

run_report 'prefect-acceptance-fixture/local' "$NORMAL_PARAMS" 600 "$REPORT_DIR/normal-2.json"
[[ "$(json_field "$REPORT_DIR/normal-2.json" state_name)" == COMPLETED ]]
NORMAL_2_ID="$(json_field "$REPORT_DIR/normal-2.json" flow_run_id)"
summary_report "$NORMAL_2_ID" "$REPORT_DIR/normal-2-ops.json"
"$PYTHON" - "$REPORT_DIR/normal-1-ops.json" "$REPORT_DIR/normal-2-ops.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1], encoding="utf-8"))
b = json.load(open(sys.argv[2], encoding="utf-8"))
assert a["pipeline_run_id"] == b["pipeline_run_id"], (a, b)
assert a["receipt_artifact_id"] == b["receipt_artifact_id"], (a, b)
assert a["stage_count"] == b["stage_count"] > 0, (a, b)
assert a["stage_attempts"] == b["stage_attempts"], (a, b)
assert all(item["output_count"] > 0 for item in a["stage_attempts"]), a
print("PREFECT_FLOW_IDEMPOTENCY=PASS")
print("PREFECT_STAGE_IDEMPOTENCY=PASS")
print("PIPELINE_RECEIPT_IDEMPOTENCY=PASS")
PY

CURRENT_STEP="transient-retry"
TRANSIENT_PARAMS="$(make_parameters standard transient-once 0 transient-retry)"
run_report 'prefect-acceptance-fixture/local' "$TRANSIENT_PARAMS" 600 "$REPORT_DIR/transient.json"
[[ "$(json_field "$REPORT_DIR/transient.json" state_name)" == COMPLETED ]]
TRANSIENT_ID="$(json_field "$REPORT_DIR/transient.json" flow_run_id)"
summary_report "$TRANSIENT_ID" "$REPORT_DIR/transient-ops.json"
"$PYTHON" - "$REPORT_DIR/transient-ops.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
attempts = r["stage_attempts"]
assert len(attempts) == 2, attempts
assert [x["status"] for x in attempts] == ["FAILED", "SUCCEEDED"], attempts
print("PREFECT_TRANSIENT_RETRY=PASS")
PY

CURRENT_STEP="contract-failure-no-retry"
CONTRACT_PARAMS="$(make_parameters standard contract-failure 0 contract-failure)"
run_report 'prefect-acceptance-fixture/local' "$CONTRACT_PARAMS" 600 "$REPORT_DIR/contract-failure.json"
[[ "$(json_field "$REPORT_DIR/contract-failure.json" state_name)" == FAILED ]]
CONTRACT_ID="$(json_field "$REPORT_DIR/contract-failure.json" flow_run_id)"
summary_report "$CONTRACT_ID" "$REPORT_DIR/contract-failure-ops.json"
"$PYTHON" - "$REPORT_DIR/contract-failure-ops.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["pipeline_status"] == "FAILED", r
assert len(r["stage_attempts"]) == 1, r
assert r["stage_attempts"][0]["status"] == "FAILED", r
print("PREFECT_CONTRACT_FAILURE_NO_RETRY=PASS")
PY

CURRENT_STEP="cancellation"
SLEEP_PARAMS="$(make_parameters standard sleep 120 cancellation)"
run_report 'prefect-acceptance-fixture/local' "$SLEEP_PARAMS" 0 "$REPORT_DIR/cancel-created.json"
CANCEL_ID="$(json_field "$REPORT_DIR/cancel-created.json" flow_run_id)"
wait_ops_running "$CANCEL_ID" "$REPORT_DIR/cancel-bound-running.json"
"$PREFECT_CLI" flow-run cancel "$CANCEL_ID"
"$PYTHON" -m research.python.researchops.orchestration.live_acceptance wait \
  --flow-run-id "$CANCEL_ID" --timeout 180 --report-path "$REPORT_DIR/cancel-wait.json" >/dev/null
[[ "$(json_field "$REPORT_DIR/cancel-wait.json" state_name)" == CANCELLED ]]

CURRENT_STEP="approval-rejection"
REJECT_PARAMS="$(make_parameters approval normal 2 approval-reject)"
run_report 'prefect-approval-acceptance-fixture/local' "$REJECT_PARAMS" 0 "$REPORT_DIR/rejection-created.json"
REJECT_FLOW_ID="$(json_field "$REPORT_DIR/rejection-created.json" flow_run_id)"
wait_pending_approval "$REJECT_FLOW_ID" "$REPORT_DIR/pending-reject.json"
REJECTION_ID="$(json_field "$REPORT_DIR/pending-reject.json" approval_id)"
"$PYTHON" -m research.python.researchops.orchestration.approvals reject \
  --approval-id "$REJECTION_ID" --actor phase6-reviewer \
  --reason 'Intentional Phase 6 rejection acceptance' --resume-prefect \
  --resume-timeout-seconds "$APPROVAL_RESUME_TIMEOUT" \
  --resume-poll-interval-seconds "$APPROVAL_RESUME_POLL_INTERVAL" \
  --report-path "$REPORT_DIR/rejected.json" >/dev/null
[[ "$(json_field "$REPORT_DIR/rejected.json" prefect_resumed)" == True ]]
"$PYTHON" -m research.python.researchops.orchestration.live_acceptance wait \
  --flow-run-id "$REJECT_FLOW_ID" --timeout 600 \
  --report-path "$REPORT_DIR/rejection-wait.json" >/dev/null
[[ "$(json_field "$REPORT_DIR/rejection-wait.json" state_name)" == FAILED ]]
summary_report "$REJECT_FLOW_ID" "$REPORT_DIR/rejection-ops.json"
[[ "$(json_field "$REPORT_DIR/rejection-ops.json" pipeline_status)" == FAILED ]]
echo "PREFECT_APPROVAL_REJECTION=PASS"
echo "PREFECT_APPROVAL_BOUNDARY=PASS"

CURRENT_STEP="ops-prefect-reconciliation"
"$PYTHON" -m research.python.researchops.orchestration.reconciliation \
  --mode repair-safe \
  --acceptance-session "$SESSION_ID" \
  --report-path "$REPORT_DIR/reconciliation-repair.json" || true
"$PYTHON" -m research.python.researchops.orchestration.reconciliation \
  --mode report-only \
  --acceptance-session "$SESSION_ID" \
  --report-path "$REPORT_DIR/reconciliation-final.json"
"$PYTHON" - "$REPORT_DIR/reconciliation-final.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["passed"] is True, r
assert r["error_count"] == 0, r
assert r["checked_flow_runs"] == 7, r
assert r["checked_pipeline_runs"] == 6, r
print("PREFECT_RECONCILIATION_SESSION_SCOPE=PASS")
print("PREFECT_OPS_RECONCILIATION=PASS")
PY
summary_report "$CANCEL_ID" "$REPORT_DIR/cancel-ops.json"
[[ "$(json_field "$REPORT_DIR/cancel-ops.json" pipeline_status)" == CANCELLED ]]
echo "PREFECT_CANCELLATION=PASS"
echo "PREFECT_CANCEL_RETRY_POLICY=PASS"

CURRENT_STEP="mlflow-registration-flow-reuse"
MLFLOW_PARAMETERS="$(make_parameters mlflow normal 0 mlflow-registration-reuse)"
MLFLOW_INPUTS="$("$PYTHON" - "$MLFLOW_PARAMETERS" "$RESEARCHOPS_PHASE5_SOURCE_ARTIFACT_ID" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
payload["input_artifact_ids"] = {"trained_models": sys.argv[2]}
print(json.dumps(payload, separators=(",", ":")))
PY
)"
run_report 'register-verified-training-release/local' "$MLFLOW_INPUTS" 1200 "$REPORT_DIR/mlflow-flow-1.json"
run_report 'register-verified-training-release/local' "$MLFLOW_INPUTS" 1200 "$REPORT_DIR/mlflow-flow-2.json"
MLFLOW_1_ID="$(json_field "$REPORT_DIR/mlflow-flow-1.json" flow_run_id)"
MLFLOW_2_ID="$(json_field "$REPORT_DIR/mlflow-flow-2.json" flow_run_id)"
summary_report "$MLFLOW_1_ID" "$REPORT_DIR/mlflow-ops-1.json"
summary_report "$MLFLOW_2_ID" "$REPORT_DIR/mlflow-ops-2.json"
"$PYTHON" - "$REPORT_DIR/mlflow-ops-1.json" "$REPORT_DIR/mlflow-ops-2.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1], encoding="utf-8"))
b = json.load(open(sys.argv[2], encoding="utf-8"))
assert a["pipeline_status"] == b["pipeline_status"] == "SUCCEEDED", (a, b)
assert a["pipeline_run_id"] == b["pipeline_run_id"], (a, b)
assert a["receipt_artifact_id"] == b["receipt_artifact_id"], (a, b)
assert a["stage_attempts"] == b["stage_attempts"], (a, b)
print("MLFLOW_REGISTRATION_FLOW_REUSE=PASS")
PY

CURRENT_STEP="mlflow-phase5-current-state"
RESEARCHOPS_MLFLOW_CURRENT_STATE_DIR="$REPORT_DIR/mlflow-current-state" \
  scripts/researchops/mlflow_phase5_current_state_acceptance.sh
echo "MLFLOW_PHASE5_CURRENT_STATE_ACCEPTANCE=PASS"

CURRENT_STEP="deterministic-regression"
"$PYTHON" -m pytest -q tests/research/python/researchops
"$PYTHON" -m research.python.researchops.contracts validate
"$PYTHON" -m research.python.researchops.stage_registry validate
"$PYTHON" -m research.python.researchops.stage_registry compile --check
"$PYTHON" -m research.python.researchops.orchestration.flow_catalog validate
"$PYTHON" -m research.python.researchops.orchestration.flow_catalog compile --check
"$PYTHON" -m research.python.researchops.orchestration.prefect_adapter.deployment_cli compile-check
"$PYTHON" -m compileall -q research/python/researchops
git diff --check

CURRENT_STEP="finalize"
"$PYTHON" - "$REPORT_DIR/acceptance-summary.json" "$SESSION_ID" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
output, session_id = sys.argv[1:]
Path(output).write_text(
    json.dumps(
        {
            "schema_version": "phase6_live_acceptance_summary_v1",
            "passed": True,
            "session_id": session_id,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
        indent=2,
    ) + "\n",
    encoding="utf-8",
)
PY

cat <<EOF
PREFECT_PHASE6_CURRENT_STATE_ACCEPTANCE=PASS
PHASE_6A_INFRASTRUCTURE=COMPLETE
PHASE_6B_FLOW_CATALOG=COMPLETE
PHASE_6C_EXECUTION_BRIDGE=COMPLETE
PHASE_6D_OFFICIAL_FLOWS=COMPLETE
PHASE_6E_APPROVAL_RECONCILIATION=COMPLETE
PHASE_6_ORCHESTRATION=COMPLETE
PATCH_BATCH_0062_0064_LIVE_ACCEPTANCE=PASS
PHASE6_LIVE_SESSION_ID=$SESSION_ID
PHASE6_LIVE_REPORT_DIR=$REPORT_DIR
EOF
