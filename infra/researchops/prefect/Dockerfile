FROM prefecthq/prefect:3.7.8-python3.12

WORKDIR /workspace
COPY research/python/requirements-researchops.txt /tmp/requirements-researchops.txt
RUN python -m pip install --no-cache-dir \
    -r /tmp/requirements-researchops.txt

ENV PYTHONPATH=/workspace
