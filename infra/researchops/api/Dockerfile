FROM python:3.12.12-slim-bookworm

WORKDIR /workspace
COPY research/python/requirements-researchops.txt /tmp/requirements-researchops.txt
COPY research/python/requirements-control-plane.txt /tmp/requirements-control-plane.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements-control-plane.txt
COPY . /workspace
ENV PYTHONPATH=/workspace \
    PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "research.python.researchops.control_plane.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
