"""Dataset-neutral access to canonical case metadata in evidence packages.

Home Credit packages expose ``internal_metadata.customer`` while the Freddie
replication exposes ``internal_metadata.case``.  This module is the only place
where the data mart translates those source-specific envelopes into one common
case identity.  Ambiguous dual envelopes fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CaseMetadata:
    case_id: str
    row_index: Any
    selection_stratum: Any
    selection_rank: Any
    source_kind: str


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_case(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def extract_case_metadata(package: dict[str, Any]) -> CaseMetadata:
    """Return one unambiguous common case identity or raise ``ValueError``."""

    package_id = package.get("package_id")
    internal = _mapping(package.get("internal_metadata"))
    case = _mapping(internal.get("case"))
    customer = _mapping(internal.get("customer"))

    case_id = _normalize_case(case.get("case_id"))
    customer_id = _normalize_case(customer.get("SK_ID_CURR"))

    if case_id is not None and customer_id is not None:
        if case_id != customer_id:
            raise ValueError(
                "Evidence package has conflicting case/customer identities: "
                f"package_id={package_id!r}, case_id={case_id!r}, "
                f"SK_ID_CURR={customer_id!r}."
            )
        # A package carrying both envelopes is only accepted when the common
        # analytical fields also agree.  This prevents silent precedence drift.
        pairs = (
            ("row_index", case.get("row_index"), customer.get("row_index")),
            ("case_type", case.get("case_type"), customer.get("case_type")),
            (
                "selection_rank",
                case.get("selection_rank"),
                customer.get("selection_rank"),
            ),
        )
        conflicting = [name for name, left, right in pairs if left != right]
        if conflicting:
            raise ValueError(
                "Evidence package has conflicting case/customer metadata: "
                f"package_id={package_id!r}, fields={conflicting}."
            )
        return CaseMetadata(
            case_id=case_id,
            row_index=case.get("row_index"),
            selection_stratum=case.get("case_type"),
            selection_rank=case.get("selection_rank"),
            source_kind="case+customer",
        )

    if case_id is not None:
        return CaseMetadata(
            case_id=case_id,
            row_index=case.get("row_index"),
            selection_stratum=case.get("case_type"),
            selection_rank=case.get("selection_rank"),
            source_kind="case",
        )

    if customer_id is not None:
        return CaseMetadata(
            case_id=customer_id,
            row_index=customer.get("row_index"),
            selection_stratum=customer.get("case_type"),
            selection_rank=customer.get("selection_rank"),
            source_kind="customer",
        )

    raise ValueError(
        "Evidence package has no canonical case identity in "
        "internal_metadata.case.case_id or "
        "internal_metadata.customer.SK_ID_CURR: "
        f"package_id={package_id!r}."
    )
