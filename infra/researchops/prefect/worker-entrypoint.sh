#!/bin/sh
set -eu

: "${PREFECT_WORK_POOL_NAME:?}"
PREFECT_WORKER_LIMIT="${PREFECT_WORKER_LIMIT:-4}"
case "$PREFECT_WORKER_LIMIT" in
  ''|*[!0-9]*)
    echo "PREFECT_WORKER_LIMIT must be a positive integer; got: $PREFECT_WORKER_LIMIT" >&2
    exit 2
    ;;
  0)
    echo "PREFECT_WORKER_LIMIT must be greater than zero." >&2
    exit 2
    ;;
esac
export PREFECT_WORKER_LIMIT

# Host-side RESEARCHOPS_DATABASE_URL points at 127.0.0.1:5433 and cannot be
# reused by a process running inside the Compose network. Prefer an explicit,
# URL-encoded internal URL when supplied. Otherwise derive the internal URL
# from the same credentials that initialize the existing Ops database.
if [ -z "${RESEARCHOPS_DATABASE_URL:-}" ]; then
  : "${RESEARCHOPS_POSTGRES_DB:?}"
  : "${RESEARCHOPS_POSTGRES_USER:?}"
  : "${RESEARCHOPS_POSTGRES_PASSWORD:?}"
  case "$RESEARCHOPS_POSTGRES_PASSWORD" in
    *[:/@?#\[\]]*)
      echo "RESEARCHOPS_POSTGRES_PASSWORD contains URL-reserved characters." >&2
      echo "Set RESEARCHOPS_INTERNAL_DATABASE_URL with URL-encoded credentials." >&2
      exit 2
      ;;
  esac
  export RESEARCHOPS_DATABASE_URL="postgresql+psycopg://${RESEARCHOPS_POSTGRES_USER}:${RESEARCHOPS_POSTGRES_PASSWORD}@researchops-postgres:5432/${RESEARCHOPS_POSTGRES_DB}"
fi

python3 -m research.python.researchops.orchestration.ops_database_preflight \
  --report-path /tmp/researchops-prefect-ops-database-preflight.json

echo "PREFECT_OPS_DATABASE_CONNECTIVITY=PASS"

exec prefect worker start \
  --pool "$PREFECT_WORK_POOL_NAME" \
  --limit "$PREFECT_WORKER_LIMIT" \
  --with-healthcheck
