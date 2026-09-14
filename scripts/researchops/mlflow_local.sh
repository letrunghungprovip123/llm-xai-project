#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"

for file in .env.researchops-storage.local .env.researchops-db.local .env.researchops-mlflow.local; do
  if [ ! -f "$file" ]; then
    echo "Missing $file" >&2
    exit 2
  fi
  set -a
  # shellcheck disable=SC1090
  . "./$file"
  set +a
done

command="${1:-up}"
case "$command" in
  up)
    docker compose --profile researchops-mlflow up -d --build \
      researchops-mlflow-db-init \
      researchops-mlflow-minio-init \
      researchops-mlflow-migrate \
      researchops-mlflow
    ;;
  down)
    docker compose --profile researchops-mlflow stop researchops-mlflow
    ;;
  status)
    docker compose --profile researchops-mlflow ps
    ;;
  logs)
    docker compose --profile researchops-mlflow logs --tail=200 researchops-mlflow
    ;;
  bootstrap)
    python3 -m research.python.researchops.mlflow_tracking bootstrap-experiments
    ;;
  smoke)
    python3 -m research.python.researchops.mlflow_tracking smoke-test
    ;;
  *)
    echo "Usage: $0 {up|down|status|logs|bootstrap|smoke}" >&2
    exit 2
    ;;
esac
