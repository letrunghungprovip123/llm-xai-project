#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"

MODE="report-only"
if [[ "${1:-}" == "--apply" ]]; then
  MODE="apply"
elif [[ -n "${1:-}" ]]; then
  echo "Usage: $0 [--apply]" >&2
  exit 2
fi

PYTHON="${RESEARCHOPS_PYTHON:-$ROOT/.venv/bin/python3}"
PREFECT_CLI="${RESEARCHOPS_PREFECT_CLI:-$ROOT/.venv/bin/prefect}"
REPORT_DIR="${RESEARCHOPS_PREFECT_CLEANUP_DIR:-/tmp/researchops-prefect-phase6-cleanup/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$REPORT_DIR"

for file in .env.researchops-db.local .env.researchops-prefect.local; do
  [[ -f "$file" ]] || { echo "ERROR: missing $file" >&2; exit 2; }
  set -a
  # shellcheck disable=SC1090
  source "$file"
  set +a
done

"$PYTHON" -m research.python.researchops.orchestration.approvals list \
  --report-path "$REPORT_DIR/approvals.json" >/dev/null

"$PYTHON" - "$REPORT_DIR/approvals.json" "$REPORT_DIR/candidates.tsv" <<'PY'
import json
import re
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
report = json.loads(source.read_text(encoding="utf-8"))
valid = re.compile(r"^[a-z0-9-]+$")
rows = []
for approval in report.get("approvals", []):
    details = approval.get("details") or {}
    resume_key = str(details.get("resume_key") or "")
    flow_run_id = str(details.get("prefect_flow_run_id") or "")
    if not flow_run_id or not resume_key or valid.fullmatch(resume_key):
        continue
    rows.append(
        (
            str(approval.get("id") or ""),
            flow_run_id,
            str(approval.get("pipeline_run_id") or ""),
            str(approval.get("status") or ""),
            resume_key,
        )
    )
target.write_text(
    "".join("\t".join(row) + "\n" for row in rows),
    encoding="utf-8",
)
print(f"PREFECT_STRANDED_APPROVAL_CANDIDATES={len(rows)}")
PY

: > "$REPORT_DIR/actions.tsv"
while IFS=$'\t' read -r approval_id flow_run_id pipeline_run_id status resume_key; do
  [[ -n "$flow_run_id" ]] || continue
  summary="$REPORT_DIR/ops-${flow_run_id}.json"
  if ! "$PYTHON" -m research.python.researchops.orchestration.live_acceptance \
      ops-summary --flow-run-id "$flow_run_id" --report-path "$summary" >/dev/null 2>&1; then
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$approval_id" "$flow_run_id" "skipped-no-ops-binding" "$status" "$resume_key" \
      >> "$REPORT_DIR/actions.tsv"
    continue
  fi

  read -r flow_id pipeline_status < <(
    "$PYTHON" - "$summary" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
print(payload.get("flow_id", "-"), payload.get("pipeline_status", "-"))
PY
  )

  if [[ "$flow_id" != "prefect_approval_acceptance_fixture" ]]; then
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$approval_id" "$flow_run_id" "skipped-non-fixture" "$status" "$resume_key" \
      >> "$REPORT_DIR/actions.tsv"
    continue
  fi

  if [[ "$pipeline_status" != "WAITING_APPROVAL" && "$pipeline_status" != "RUNNING" ]]; then
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$approval_id" "$flow_run_id" "skipped-terminal-ops-state" "$status" "$resume_key" \
      >> "$REPORT_DIR/actions.tsv"
    continue
  fi

  if [[ "$MODE" == "apply" ]]; then
    if "$PREFECT_CLI" flow-run cancel "$flow_run_id"; then
      action="cancellation-requested"
    else
      action="cancellation-request-failed"
    fi
  else
    action="would-cancel"
  fi
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$approval_id" "$flow_run_id" "$action" "$status" "$resume_key" \
    >> "$REPORT_DIR/actions.tsv"
done < "$REPORT_DIR/candidates.tsv"

"$PYTHON" - "$MODE" "$REPORT_DIR/actions.tsv" "$REPORT_DIR/cleanup-report.json" <<'PY'
import json
import sys
from pathlib import Path

mode, actions_path, output_path = sys.argv[1:]
actions = []
for line in Path(actions_path).read_text(encoding="utf-8").splitlines():
    approval_id, flow_run_id, action, status, resume_key = line.split("\t", 4)
    actions.append(
        {
            "approval_id": approval_id,
            "prefect_flow_run_id": flow_run_id,
            "action": action,
            "approval_status": status,
            "legacy_resume_key": resume_key,
        }
    )
report = {
    "schema_version": "phase6_stranded_approval_cleanup_v1",
    "mode": mode,
    "fixture_only": True,
    "direct_database_mutation": False,
    "action_count": len(actions),
    "actions": actions,
    "passed": not any(item["action"] == "cancellation-request-failed" for item in actions),
}
Path(output_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
if not report["passed"]:
    raise SystemExit("One or more safe cancellation requests failed")
print("PREFECT_STRANDED_APPROVAL_CLEANUP_REPORT=PASS")
PY

echo "PREFECT_STRANDED_APPROVAL_CLEANUP_MODE=$MODE"
echo "PREFECT_STRANDED_APPROVAL_CLEANUP_REPORT=$REPORT_DIR/cleanup-report.json"
