from __future__ import annotations
from pathlib import Path
from research.python.common.paths import DEFAULT_PATHS

PROJECT_ROOT=DEFAULT_PATHS.project_root
VISUALIZATION_RELEASE_ID="visualization-data-v3"
VISUALIZATION_VERSION="v3.0"
VISUALIZATION_DATA_DIR=PROJECT_ROOT/"data/reports/llm_validation/multidataset_replication_v1/visualization_v3"
VISUALIZATION_MANIFEST_PATH=VISUALIZATION_DATA_DIR/"visualization_manifest.json"
VISUALIZATION_VALIDATION_PATH=VISUALIZATION_DATA_DIR/"visualization_validation.json"
DASHBOARD_ASSETS_DIR=PROJECT_ROOT/"research/python/dashboard/assets"
DEFAULT_HOST="127.0.0.1"; DEFAULT_PORT=8051
DATASET_SCOPES=("HOME_CREDIT","FREDDIE","CROSS_DATASET")
DEFAULT_DATASET_SCOPE="CROSS_DATASET"
PAGE_ORDER=("overview","effectiveness","mechanisms","decision","robustness","cases","methods")
PAGE_PATHS={"overview":"/","effectiveness":"/effectiveness","mechanisms":"/mechanisms","decision":"/decision","robustness":"/robustness","cases":"/cases","methods":"/methods"}
