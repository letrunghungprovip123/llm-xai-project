#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="$ROOT/.venv/bin/python3"
REPORT_DIR="${RESEARCHOPS_PREFECT_ACCEPTANCE_DIR:-/tmp/researchops-prefect-phase6a}"
DB_ENV=.env.researchops-db.local
PREFECT_ENV=.env.researchops-prefect.local
mkdir -p "$REPORT_DIR"

[[ -x "$PYTHON" ]] || { echo "ERROR: missing $PYTHON" >&2; exit 2; }
[[ -f "$DB_ENV" ]] || { echo "ERROR: missing $DB_ENV" >&2; exit 2; }
if [[ ! -f "$PREFECT_ENV" ]]; then
  "$PYTHON" -m research.python.researchops.orchestration \
    init-local-env --output "$PREFECT_ENV"
fi
chmod 600 "$PREFECT_ENV"
for file in "$DB_ENV" "$PREFECT_ENV"; do
  set -a
  # shellcheck disable=SC1090
  source "$file"
  set +a
done

if git status --short --untracked-files=all | grep -F "$PREFECT_ENV"; then
  echo "ERROR: $PREFECT_ENV appears in Git status" >&2
  exit 2
fi

"$PYTHON" -m research.python.researchops.orchestration validate-runtime \
  --report-path "$REPORT_DIR/runtime-contract.json" >/dev/null
"$PYTHON" -m pytest -q tests/research/python/researchops/orchestration
"$PYTHON" -m research.python.researchops.stage_registry compile --check

python3 - <<'PY'
import yaml
from pathlib import Path
payload=yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
required={
    "researchops-prefect-db-init",
    "researchops-prefect-redis",
    "researchops-prefect-migrate",
    "researchops-prefect-server",
    "researchops-prefect-services",
    "researchops-prefect-bootstrap",
    "researchops-prefect-worker",
}
assert required <= set(payload["services"]), required-set(payload["services"])
print("PREFECT_COMPOSE_CONTRACT=PASS")
PY

scripts/researchops/prefect_local.sh up
for attempt in $(seq 1 120); do
  server="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' llm-xai-researchops-prefect-server 2>/dev/null || true)"
  worker="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' llm-xai-researchops-prefect-worker 2>/dev/null || true)"
  echo "Prefect server=$server worker=$worker"
  [[ "$server" == healthy && "$worker" == healthy ]] && break
  sleep 2
done
[[ "${server:-}" == healthy && "${worker:-}" == healthy ]] || {
  scripts/researchops/prefect_local.sh logs
  exit 1
}

docker inspect --format='{{.State.ExitCode}}' llm-xai-researchops-prefect-db-init | grep -Fxq 0
docker inspect --format='{{.State.ExitCode}}' llm-xai-researchops-prefect-migrate | grep -Fxq 0
docker inspect --format='{{.State.ExitCode}}' llm-xai-researchops-prefect-bootstrap | grep -Fxq 0
docker inspect --format='{{.State.Status}}' llm-xai-researchops-prefect-redis | grep -Fxq running
docker inspect --format='{{.State.Status}}' llm-xai-researchops-prefect-services | grep -Fxq running

echo "PREFECT_DATABASE_MIGRATION=PASS"
echo "PREFECT_REDIS_HEALTH=PASS"
echo "PREFECT_API_HEALTH=PASS"
echo "PREFECT_BACKGROUND_SERVICES=PASS"
echo "PREFECT_WORKER_HEALTH=PASS"

"$PYTHON" -m research.python.researchops.orchestration bootstrap-runtime \
  --report-path "$REPORT_DIR/bootstrap.json" >/dev/null
"$PYTHON" -m research.python.researchops.orchestration inspect-runtime \
  --report-path "$REPORT_DIR/runtime.json" >/dev/null

"$PYTHON" - "$REPORT_DIR/bootstrap.json" "$REPORT_DIR/runtime.json" <<'PY'
import json, sys
bootstrap=json.load(open(sys.argv[1], encoding="utf-8"))
runtime=json.load(open(sys.argv[2], encoding="utf-8"))
assert bootstrap["passed"] is True and bootstrap["idempotent"] is True
assert runtime["passed"] is True
assert runtime["client_version"] == runtime["server_version"] == "3.7.8"
assert runtime["work_pool_name"] == "researchops-local-process"
assert runtime["work_pool_type"] == "process"
expected={
    "release": (1, 1),
    "provider-llm": (2, 1),
    "cpu-heavy": (5, 1),
    "verification": (10, 4),
}
observed={
    item["name"]: (item["priority"], item["concurrency_limit"])
    for item in runtime["queues"]
}
assert observed == expected, observed
assert runtime["online_workers"], runtime
print("PREFECT_CLIENT_SERVER_VERSION=PASS")
print("PREFECT_WORK_POOL_POLICY=PASS")
print("PREFECT_QUEUE_POLICY=PASS")
print("PREFECT_WORKER_HEARTBEAT=PASS")
PY

"$PYTHON" -m pytest -q tests/research/python/researchops
"$PYTHON" -m compileall -q research/python/researchops
git diff --check

echo "PHASE_6A_INFRASTRUCTURE=COMPLETE"
