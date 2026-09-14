"""Explicit registration of the seven-page research architecture."""

from . import cases, decision, effectiveness, mechanisms, methods, overview, robustness


def register_pages() -> None:
    for module in (
        overview,
        effectiveness,
        mechanisms,
        decision,
        robustness,
        cases,
        methods,
    ):
        module.register_page()
