"""Custom content helper for unknown routes."""
from __future__ import annotations
from ..components.empty_state import empty_state
def layout():
    return empty_state("Page not found", "Use the research journey navigation to return to a certified dashboard page.")
