from research.python.researchops.orchestration.execution.errors import (
    HashMismatchError,
    RateLimitError,
    TransientNetworkError,
    classify_error,
)
from research.python.researchops.orchestration.prefect_adapter.tasks import should_retry_exception


def test_only_transient_errors_are_retryable():
    assert should_retry_exception(TransientNetworkError("temporary"))
    assert should_retry_exception(RateLimitError("slow down"))
    assert not should_retry_exception(HashMismatchError("corrupt"))
    assert not should_retry_exception(ValueError("unknown"))
    assert classify_error(HashMismatchError("bad")).category == "HASH_MISMATCH"
