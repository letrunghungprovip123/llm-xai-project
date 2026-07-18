# syntax=docker/dockerfile:1.7
ARG VLLM_IMAGE=vllm/vllm-openai:v0.21.0

FROM node:20-bookworm-slim AS node_builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run typecheck:batch-i


FROM ${VLLM_IMAGE} AS runtime

USER root

ARG SOURCE_REVISION=unknown

COPY --from=node_builder /usr/local/ /usr/local/
COPY --from=node_builder /app /app

WORKDIR /app

COPY infra/aws-batch/entrypoint.sh \
    /usr/local/bin/batch-i-entrypoint

COPY infra/aws-batch/telemetry/gpu-monitor.sh \
    /usr/local/bin/batch-i-gpu-monitor

COPY infra/aws-batch/telemetry/runtime-metadata.sh \
    /usr/local/bin/batch-i-runtime-metadata

RUN chmod +x \
      /usr/local/bin/batch-i-entrypoint \
      /usr/local/bin/batch-i-gpu-monitor \
      /usr/local/bin/batch-i-runtime-metadata \
    && mkdir -p \
      /work/huggingface \
      /work/vllm \
      /work/tmp

ENV NODE_ENV=production \
    VLLM_BASE_URL=http://127.0.0.1:8000/v1 \
    HF_HOME=/work/huggingface \
    HUGGINGFACE_HUB_CACHE=/work/huggingface/hub \
    VLLM_CACHE_ROOT=/work/vllm \
    TMPDIR=/work/tmp \
    PYTHONUNBUFFERED=1 \
    SOURCE_REVISION=${SOURCE_REVISION} \
    GPU_MONITOR_INTERVAL_SECONDS=10

LABEL org.opencontainers.image.revision="${SOURCE_REVISION}"

ENTRYPOINT ["/usr/local/bin/batch-i-entrypoint"]
