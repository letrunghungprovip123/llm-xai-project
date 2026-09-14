from __future__ import annotations
from . import cases, decision, effectiveness, mechanisms, methods, overview, robustness


def register_pages_v3()->None:
    overview.register_page()
    effectiveness.register_page()
    mechanisms.register_page()
    decision.register_page()
    robustness.register_page()
    cases.register_page()
    methods.register_page()
