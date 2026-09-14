#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
ACTION="${1:-status}"
case "$ACTION" in
  start)
    docker compose --profile researchops-prefect up -d --build researchops-api
    ;;
  stop)
    docker compose stop researchops-api
    ;;
  logs)
    docker compose logs -f researchops-api
    ;;
  status)
    docker compose ps researchops-api
    ;;
  *)
    echo "usage: $0 {start|stop|logs|status}" >&2
    exit 2
    ;;
esac
