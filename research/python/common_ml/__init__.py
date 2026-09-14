"""Dataset-neutral common ML path for credit-risk replication.

This package is intentionally additive. Legacy Home Credit Batch D/E/F entrypoints
remain untouched; new dataset-aware runs opt into this path explicitly.
"""

from .context import CommonMLRunContext

__all__ = ["CommonMLRunContext"]
