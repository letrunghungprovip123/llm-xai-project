"""Machine-readable governance contract loading and validation."""

from .validation import ContractValidationReport, validate_all_contracts

__all__ = ["ContractValidationReport", "validate_all_contracts"]
