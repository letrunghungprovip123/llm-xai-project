#!/bin/sh
set -eu
cd /workspace
python -m research.python.researchops.orchestration bootstrap-runtime \
  --report-path /tmp/prefect-runtime-bootstrap.json
cat /tmp/prefect-runtime-bootstrap.json
