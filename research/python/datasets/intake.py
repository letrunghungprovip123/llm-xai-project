"""Dataset-profile preflight for exact multi-dataset LLM-XAI replication.

This is intentionally a *profile/canonical-bundle* gate, not a substitute for
raw-data audit.  It catches structural incompatibilities before engineering an
adapter, while leaving licensing, leakage and source-specific data quality to
the dataset-specific intake audit (M11 proper).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import CanonicalDatasetBundle, DatasetProfile


PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass(frozen=True)
class EligibilityCheck:
    check_id: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ReplicationProfileReport:
    status: str
    dataset_id: str
    checks: tuple[EligibilityCheck, ...]

    @property
    def failures(self) -> tuple[EligibilityCheck, ...]:
        return tuple(check for check in self.checks if check.status == FAIL)

    @property
    def warnings(self) -> tuple[EligibilityCheck, ...]:
        return tuple(check for check in self.checks if check.status == WARN)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "dataset_replication_profile_report_v1",
            "dataset_id": self.dataset_id,
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
        }


def _overall_status(checks: Iterable[EligibilityCheck]) -> str:
    values = [check.status for check in checks]
    if FAIL in values:
        return FAIL
    if WARN in values:
        return WARN
    return PASS


def evaluate_replication_profile(
    profile: DatasetProfile,
    bundle: CanonicalDatasetBundle | None = None,
    *,
    require_explicit_target_semantics: bool = True,
    recommended_min_feature_count: int = 20,
) -> ReplicationProfileReport:
    """Evaluate whether a profile is structurally suitable for the exact study.

    The gate deliberately does not inspect raw rows.  A PASS here means the
    *contract* is suitable for onboarding; it does not certify absence of
    leakage, adequate class counts, licensing, or the later 36-case cohort.
    """

    checks: list[EligibilityCheck] = []
    checks.append(
        EligibilityCheck(
            "credit_risk_binary_task",
            PASS if profile.domain == "credit_risk" and profile.task_type == "binary_classification" else FAIL,
            f"domain={profile.domain}; task_type={profile.task_type}",
        )
    )

    capability_checks = (
        ("stable_entity_identity", profile.capabilities.has_stable_entity_id),
        ("feature_level_xai", profile.capabilities.supports_feature_level_xai),
        ("semantic_registry", profile.capabilities.supports_semantic_registry),
        ("case_strata", profile.capabilities.supports_case_strata),
        ("adaptive_evidence", profile.capabilities.supports_adaptive_evidence),
    )
    for check_id, enabled in capability_checks:
        checks.append(
            EligibilityCheck(
                check_id,
                PASS if enabled else FAIL,
                "declared supported" if enabled else "required capability is disabled",
            )
        )

    feature_count = profile.capabilities.feature_count
    if feature_count is None:
        feature_status = FAIL
        feature_detail = "feature_count is missing; S0-S5 separability cannot be screened"
    elif feature_count <= 10:
        feature_status = FAIL
        feature_detail = (
            f"feature_count={feature_count}; S1 top-10 would expose the full or nearly full feature universe"
        )
    elif feature_count < recommended_min_feature_count:
        feature_status = WARN
        feature_detail = (
            f"feature_count={feature_count}; below recommended {recommended_min_feature_count}, "
            "so adaptive evidence separability needs extra scrutiny"
        )
    else:
        feature_status = PASS
        feature_detail = f"feature_count={feature_count}; adequate for S0-S5 preflight"
    checks.append(EligibilityCheck("feature_richness", feature_status, feature_detail))

    explicit_semantics = profile.target.prediction_semantics is not None
    semantics_status = (
        PASS
        if explicit_semantics or not require_explicit_target_semantics
        else FAIL
    )
    semantics_detail = (
        "endpoint-specific prediction semantics explicitly defined"
        if explicit_semantics
        else (
            "legacy target semantics fallback accepted for compatibility"
            if not require_explicit_target_semantics
            else "new replication datasets must explicitly define prediction_semantics"
        )
    )
    checks.append(
        EligibilityCheck("explicit_target_semantics", semantics_status, semantics_detail)
    )

    checks.append(
        EligibilityCheck(
            "prediction_horizon_documented",
            PASS if profile.target.prediction_horizon else WARN,
            (
                f"prediction_horizon={profile.target.prediction_horizon}"
                if profile.target.prediction_horizon
                else "prediction_horizon is null; endpoint comparability must be documented explicitly"
            ),
        )
    )

    if bundle is not None:
        identity_ok = (
            profile.dataset_id == bundle.dataset_id
            and profile.dataset_version == bundle.dataset_version
        )
        checks.append(
            EligibilityCheck(
                "canonical_bundle_identity",
                PASS if identity_ok else FAIL,
                (
                    f"profile={profile.dataset_id}/{profile.dataset_version}; "
                    f"bundle={bundle.dataset_id}/{bundle.dataset_version}"
                ),
            )
        )
        required = {
            "feature_matrix",
            "target",
            "feature_registry_csv",
            "feature_registry_yaml",
            "concept_registry_yaml",
        }
        missing = sorted(required - set(bundle.artifacts))
        checks.append(
            EligibilityCheck(
                "canonical_bundle_artifacts",
                PASS if not missing else FAIL,
                "all required canonical artifacts declared"
                if not missing
                else f"missing canonical artifacts: {missing}",
            )
        )

    return ReplicationProfileReport(
        status=_overall_status(checks),
        dataset_id=profile.dataset_id,
        checks=tuple(checks),
    )
