from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_compat_module():
    path = Path("infra/researchops/mlflow/sitecustomize.py")
    spec = importlib.util.spec_from_file_location("researchops_mlflow_sitecustomize", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_version_coercion_is_narrow_and_deterministic():
    module = _load_compat_module()

    assert module.coerce_model_version("1") == 1
    assert module.coerce_model_version(" 42 ") == 42
    assert module.coerce_model_version(7) == 7
    assert module.coerce_model_version(True) is True
    assert module.coerce_model_version("candidate") == "candidate"
    assert module.coerce_model_version("1.0") == "1.0"
