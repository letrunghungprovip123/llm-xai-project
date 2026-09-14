from __future__ import annotations

from dataclasses import dataclass


class OrchestrationError(RuntimeError):
    retryable = False
    category = "ORCHESTRATION"


class TransientNetworkError(OrchestrationError):
    retryable = True
    category = "TRANSIENT_NETWORK"


class TransientProviderError(OrchestrationError):
    retryable = True
    category = "TRANSIENT_PROVIDER"


class RateLimitError(OrchestrationError):
    retryable = True
    category = "RATE_LIMIT"


class InfrastructureUnavailableError(OrchestrationError):
    retryable = True
    category = "INFRASTRUCTURE_UNAVAILABLE"


class SchemaContractError(OrchestrationError):
    category = "SCHEMA_CONTRACT"


class HashMismatchError(OrchestrationError):
    category = "HASH_MISMATCH"


class ArtifactCorruptionError(OrchestrationError):
    category = "ARTIFACT_CORRUPTION"


class PolicyDeniedError(OrchestrationError):
    category = "POLICY_DENIED"


class ApprovalRejectedError(OrchestrationError):
    category = "APPROVAL_REJECTED"


class CommandConfigurationError(OrchestrationError):
    category = "COMMAND_CONFIGURATION"


class CommandExecutionError(OrchestrationError):
    category = "COMMAND_EXECUTION"

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class CommandTimeoutError(InfrastructureUnavailableError):
    category = "COMMAND_TIMEOUT"


@dataclass(frozen=True)
class ErrorClassification:
    error_type: str
    category: str
    retryable: bool
    message: str


def classify_error(exc: BaseException) -> ErrorClassification:
    if isinstance(exc, OrchestrationError):
        return ErrorClassification(
            error_type=type(exc).__name__,
            category=exc.category,
            retryable=exc.retryable,
            message=str(exc),
        )
    return ErrorClassification(
        error_type=type(exc).__name__,
        category="UNCLASSIFIED",
        retryable=False,
        message=str(exc),
    )
