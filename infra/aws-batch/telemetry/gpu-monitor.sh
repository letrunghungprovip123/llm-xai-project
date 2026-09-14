#!/usr/bin/env bash
set -Eeuo pipefail

INTERVAL_SECONDS="${GPU_MONITOR_INTERVAL_SECONDS:-10}"

echo '[AUDIT] {"event":"gpu_monitor_started","interval_seconds":'"${INTERVAL_SECONDS}"'}'

while true; do
  nvidia-smi \
    --query-gpu=timestamp,index,name,uuid,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,temperature.gpu,clocks.sm \
    --format=csv,noheader,nounits \
  | while IFS= read -r row; do
      printf '[GPU_METRIC] %s\n' "$row"
    done

  sleep "$INTERVAL_SECONDS"
done
