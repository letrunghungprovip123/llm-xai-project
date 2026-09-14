#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"

for file in .env.researchops-db.local .env.researchops-prefect.local; do
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
    docker compose --profile researchops-prefect up -d --build \
      researchops-prefect-db-init \
      researchops-prefect-redis \
      researchops-prefect-migrate \
      researchops-prefect-server \
      researchops-prefect-services \
      researchops-prefect-bootstrap \
      researchops-prefect-worker
    ;;
  stop)
    docker compose --profile researchops-prefect stop \
      researchops-prefect-worker \
      researchops-prefect-services \
      researchops-prefect-server \
      researchops-prefect-redis
    ;;
  status)
    docker compose --profile researchops-prefect ps
    ;;
  logs)
    docker compose --profile researchops-prefect logs --tail=250 \
      researchops-prefect-server \
      researchops-prefect-services \
      researchops-prefect-worker
    ;;
  bootstrap)
    python3 -m research.python.researchops.orchestration bootstrap-runtime
    ;;
  *)
    echo "Usage: $0 {up|stop|status|logs|bootstrap}" >&2
    exit 2
    ;;
esac
