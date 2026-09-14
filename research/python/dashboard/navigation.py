"""Seven-page research-first information architecture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NavigationItem:
    """Locale-neutral navigation identity."""

    key: str
    path: str
    icon: str
    order: int

    @property
    def label_key(self) -> str:
        return f"domain.page.{self.key}"

    @property
    def description_key(self) -> str:
        return f"navigation.page_description.{self.key}"


NAVIGATION_ITEMS = (
    NavigationItem("overview", "/", "solar:home-2-linear", 0),
    NavigationItem("effectiveness", "/effectiveness", "solar:chart-2-linear", 1),
    NavigationItem(
        "mechanisms", "/mechanisms", "solar:layers-minimalistic-linear", 2
    ),
    NavigationItem("decision", "/decision", "solar:ranking-linear", 3),
    NavigationItem(
        "robustness", "/robustness", "solar:shield-check-linear", 4
    ),
    NavigationItem("cases", "/cases", "solar:magnifer-linear", 5),
    NavigationItem("methods", "/methods", "solar:document-text-linear", 6),
)
