from __future__ import annotations

import pytest

from research.python.researchops.mlflow_tracking.exceptions import MLflowIntegrityError
from research.python.researchops.mlflow_tracking.model_uri import (
    is_canonical_logged_model_uri,
    is_historical_run_model_uri,
    receipt_model_uri_is_supported,
    require_canonical_logged_model_uri,
)


def test_canonical_uri_contract_accepts_only_mlflow3_logged_models():
    assert is_canonical_logged_model_uri("models:/m-abc_123")
    assert not is_canonical_logged_model_uri("runs:/run-1/model")
    with pytest.raises(MLflowIntegrityError):
        require_canonical_logged_model_uri("runs:/run-1/model")


def test_historical_receipt_uri_remains_readable_only():
    assert is_historical_run_model_uri("runs:/run-1/model")
    assert receipt_model_uri_is_supported("runs:/run-1/model")
    assert receipt_model_uri_is_supported("models:/m-abc")
    assert not receipt_model_uri_is_supported("s3://bucket/model")
