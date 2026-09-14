class MLflowIntegrationError(RuntimeError):
    """Base error for governed MLflow integration failures."""


class MLflowConfigurationError(MLflowIntegrationError):
    """Configuration is missing, inconsistent, or unsafe."""


class MLflowContractError(MLflowIntegrationError):
    """A versioned tracking or registry contract is invalid."""


class MLflowIntegrityError(MLflowIntegrationError):
    """Cross-system identity or immutable provenance does not match."""
