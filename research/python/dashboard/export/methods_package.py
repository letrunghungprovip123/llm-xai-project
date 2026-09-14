"""Export the certified Page-7 methods package."""

from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
import json
import zipfile

import pandas as pd

from ..data.repository import DashboardRepository, get_dashboard_repository
from ..i18n import (
    DEFAULT_LOCALE,
    localize_text,
    methods_identifier_label,
    normalize_locale,
    reporting_role_label,
    t,
    visibility_tier_label,
)
from .localization import export_readme


_METHODS_PREFIXES = ("methods.", "common.", "domain.")


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")


def _research_question_frame(data) -> pd.DataFrame:
    rows = []
    for item in data.research_questions:
        row = asdict(item)
        for field in [
            "primary_metrics",
            "supporting_metrics",
            "primary_sources",
            "dashboard_pages",
            "interpretation_restrictions",
        ]:
            row[field] = json.dumps(row[field], ensure_ascii=False)
        rows.append(row)
    return pd.DataFrame(rows)


def _gate_frame(data) -> pd.DataFrame:
    return pd.DataFrame([asdict(item) for item in data.validation_gates])


def _localized_methods_display_frames(data, locale: object) -> dict[str, pd.DataFrame]:
    """Build presentation-only CSV copies without mutating certified tables."""

    resolved = normalize_locale(locale)

    numbers = data.certified_numbers.copy()
    numbers.insert(
        1,
        "metric_label",
        numbers["metric_id"].map(lambda value: methods_identifier_label(resolved, value)),
    )
    numbers["report_section_label"] = numbers["report_section"].map(
        lambda value: localize_text(value, resolved, prefixes=_METHODS_PREFIXES)
    )
    numbers["reporting_role_label"] = numbers["reporting_role"].map(
        lambda value: reporting_role_label(resolved, value)
    )
    numbers["denominator_label"] = numbers["denominator"].map(
        lambda value: localize_text(value, resolved, prefixes=_METHODS_PREFIXES)
    )

    questions = _research_question_frame(data).copy()
    for column in ["title", "question", "population", "inference_unit"]:
        questions[column] = questions[column].map(
            lambda value: localize_text(value, resolved, prefixes=_METHODS_PREFIXES)
        )
    questions["interpretation_restrictions"] = questions[
        "interpretation_restrictions"
    ].map(
        lambda value: json.dumps(
            [
                localize_text(item, resolved, prefixes=_METHODS_PREFIXES)
                for item in json.loads(value)
            ],
            ensure_ascii=False,
        )
    )

    visibility = data.metric_visibility.copy()
    visibility["metric_label"] = visibility["metric_id"].map(
        lambda value: methods_identifier_label(resolved, value)
    )
    visibility["tier_label"] = visibility["visibility_tier"].map(
        lambda value: visibility_tier_label(resolved, value)
    )
    visibility["tier_description"] = visibility["visibility_tier"].map(
        lambda value: t(resolved, f"methods.visibility.{value}.description")
    )

    dictionary = data.visualization_dictionary.copy()
    dictionary.insert(
        2,
        "field_label",
        dictionary["field_name"].map(
            lambda value: methods_identifier_label(resolved, value)
        ),
    )
    dictionary["tier_label"] = dictionary["visibility_tier"].map(
        lambda value: visibility_tier_label(resolved, value)
    )

    gates = _gate_frame(data).copy()
    for column in ["layer_label", "meaning"]:
        gates[column] = gates[column].map(
            lambda value: localize_text(value, resolved, prefixes=_METHODS_PREFIXES)
        )

    artifacts = data.artifact_inventory.copy()
    artifacts["dashboard_role_label"] = artifacts["dashboard_role"].map(
        lambda value: localize_text(value, resolved, prefixes=_METHODS_PREFIXES)
    )

    limitations = data.limitations.copy()
    for column in [
        "category",
        "limitation",
        "affected_scope",
        "prevents",
        "remains_valid",
        "required_wording",
    ]:
        limitations[column] = limitations[column].map(
            lambda value: localize_text(value, resolved, prefixes=_METHODS_PREFIXES)
        )

    reproduction = data.reproduction_steps.copy()
    for column in ["step_label", "status"]:
        reproduction[column] = reproduction[column].map(
            lambda value: localize_text(value, resolved, prefixes=_METHODS_PREFIXES)
        )

    return {
        "display/certified_report_numbers.csv": numbers,
        "display/research_question_registry.csv": questions,
        "display/metric_visibility_registry.csv": visibility,
        "display/visualization_dictionary.csv": dictionary,
        "display/validation_gate_registry.csv": gates,
        "display/artifact_inventory.csv": artifacts,
        "display/limitations_registry.csv": limitations,
        "display/reproduction_steps.csv": reproduction,
    }


def build_methods_archive(
    repository: DashboardRepository | None = None,
    locale: object = DEFAULT_LOCALE,
) -> bytes:
    repo = repository or get_dashboard_repository()
    resolved_locale = normalize_locale(locale)
    data = repo.methods_data()
    manifest = {
        "schema_version": "llm_xai_methods_export_v1",
        "display_locale": resolved_locale,
        "analytical_release": data.release_audit.analytical_release_id,
        "visualization_release": data.release_audit.visualization_release_id,
        "source_commit": data.release_audit.parent_git_commit,
        "presentation_is_read_only": True,
        "browser_recomputes_inference": False,
        "claim_rows_are_independent_units": False,
        "template_is_fourth_llm": False,
        "candidate_role": "primary",
        "v4_role": "sensitivity_only",
        "human_naturalness_evaluated": False,
        "precise_template_latency_available": False,
        "raw_applicant_data_included": False,
        "files": [
            "release_metadata.csv",
            "certified_report_numbers.csv",
            "research_question_registry.csv",
            "metric_visibility_registry.csv",
            "visualization_dictionary.csv",
            "validation_gate_registry.csv",
            "artifact_inventory.csv",
            "limitations_registry.csv",
            "reproduction_steps.csv",
        ],
    }
    release = pd.DataFrame([asdict(data.release_audit)])
    files = {
        "release_metadata.csv": release,
        "certified_report_numbers.csv": data.certified_numbers,
        "research_question_registry.csv": _research_question_frame(data),
        "metric_visibility_registry.csv": data.metric_visibility,
        "visualization_dictionary.csv": data.visualization_dictionary,
        "validation_gate_registry.csv": _gate_frame(data),
        "artifact_inventory.csv": data.artifact_inventory,
        "limitations_registry.csv": data.limitations,
        "reproduction_steps.csv": data.reproduction_steps,
    }
    display_files = _localized_methods_display_frames(data, resolved_locale)
    manifest["display_files"] = sorted(display_files)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, frame in files.items():
            archive.writestr(filename, _csv_bytes(frame))
        for filename, frame in display_files.items():
            archive.writestr(filename, _csv_bytes(frame))
        archive.writestr(
            "README.txt",
            export_readme(
                resolved_locale,
                "methods",
                analytical_release=data.release_audit.analytical_release_id,
                visualization_release=data.release_audit.visualization_release_id,
                details=(
                    t(resolved_locale, "exports.common.methods_technical"),
                    t(resolved_locale, "exports.common.methods_display"),
                ),
            ),
        )
        archive.writestr(
            "methods_manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
    return buffer.getvalue()
