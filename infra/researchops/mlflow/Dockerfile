FROM ghcr.io/mlflow/mlflow:v3.14.0

# Keep the server image minimal while adding the two remote-store drivers used
# by the local ResearchOps topology.
RUN python -m pip install --no-cache-dir \
    "psycopg[binary]>=3.2,<4" \
    "boto3>=1.43,<2"

# MLflow 3.14.0 transports model-version numbers as strings while its
# PostgreSQL ORM column is INTEGER. Load a version-gated compatibility shim
# before the CLI/server imports MLflow.
COPY infra/researchops/mlflow/sitecustomize.py /opt/researchops/mlflow-compat/sitecustomize.py
ENV PYTHONPATH=/opt/researchops/mlflow-compat
