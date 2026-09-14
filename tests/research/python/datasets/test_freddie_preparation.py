from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from research.python.datasets.freddie_sflld.preparation import (
    FeaturePolicy,
    FreddieMacSFLLDPreparationAdapter,
    normalize_feature,
)
from research.python.datasets.freddie_sflld.raw_intake import FreddieRawIntakeAuditor, QUARTERS
from research.python.datasets.freddie_sflld.target_builder import FreddieTargetBuilder

ROOT = Path(__file__).resolve().parents[4]
PROFILE = ROOT / "config/research/datasets/freddie_sflld_2024_v1.json"
POLICY = ROOT / "config/research/datasets/freddie_sflld_2024_feature_policy_v1.json"
CONCEPTS = ROOT / "config/research/datasets/freddie_sflld_2024_concept_registry_v1.yaml"
PROTOCOL = ROOT / "config/research/datasets/freddie_sflld_2024_target_protocol_v1.json"


def _orig_line(quarter: str, idx: int, *, fico: str = "760") -> str:
    q = int(quarter[-1])
    first_payment = {1: "202401", 2: "202404", 3: "202407", 4: "202410"}[q]
    loan_id = f"F24Q{q}{idx:08d}"
    cols = [""] * 31
    values = {
        0: fico,
        1: first_payment,
        2: "Y" if idx % 2 else "N",
        3: "205401",
        4: "",
        5: "0",
        6: "1",
        7: "P",
        8: "80",
        9: "35",
        10: "300000",
        11: "80",
        12: "6.500",
        13: "R",
        14: "N",
        15: "FRM",
        16: "CA",
        17: "SF",
        18: "900",
        19: loan_id,
        20: "P",
        21: "360",
        22: "2",
        23: "OTHER",
        24: "N",
        25: "",
        26: "",
        27: "N",
        28: "1",
        29: "N",
        30: "9999",
    }
    for pos, value in values.items():
        cols[pos] = value
    return "|".join(cols)


def _add_month(first: str, offset: int) -> str:
    year, month = int(first[:4]), int(first[4:])
    ordinal = year * 12 + month - 1 + offset
    return f"{ordinal // 12:04d}{ordinal % 12 + 1:02d}"


def _perf_line(loan_id: str, period: str, *, status: str = "00", zbc: str = "") -> str:
    cols = [""] * 35
    cols[0] = loan_id
    cols[1] = period
    cols[2] = "300000"
    cols[3] = status
    cols[4] = "1"  # deliberately irrelevant; target is NOT anchored to raw Loan Age
    cols[8] = zbc
    return "|".join(cols)


def _make_raw_fixture(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as outer:
        for quarter in QUARTERS:
            q = int(quarter[-1])
            first = {1: "202401", 2: "202404", 3: "202407", 4: "202410"}[q]
            ids = [f"F24Q{q}{idx:08d}" for idx in (1, 2)]
            orig = "\n".join(
                [_orig_line(quarter, 1), _orig_line(quarter, 2, fico="9999" if q == 1 else "760")]
            ) + "\n"
            perf_rows: list[str] = []
            for idx, loan_id in enumerate(ids, start=1):
                for month in range(1, 13):
                    status = "03" if idx == 1 and month == 5 else "00"
                    perf_rows.append(_perf_line(loan_id, _add_month(first, month - 1), status=status))
            nested_path = path.parent / f"nested_{quarter}.zip"
            with zipfile.ZipFile(nested_path, "w", compression=zipfile.ZIP_DEFLATED) as nested:
                nested.writestr(f"orig_{quarter}.txt", orig)
                nested.writestr(f"perf_{quarter}.txt", "\n".join(perf_rows) + "\n")
            outer.write(nested_path, arcname=f"historical_data_{quarter}.zip")
            nested_path.unlink()


@pytest.fixture(autouse=True)
def _parquet_shim(monkeypatch: pytest.MonkeyPatch) -> None:
    def write_pickle(self: pd.DataFrame, path, index: bool = False, **kwargs) -> None:
        frame = self.reset_index(drop=True) if not index else self
        frame.to_pickle(path)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", write_pickle)


def test_explicit_sentinel_normalization_and_unexpected_value_failure() -> None:
    policy = FeaturePolicy.load(POLICY)
    fico = next(item for item in policy.primary_features if item.feature_name == "classic_fico")
    normalized = normalize_feature(pd.Series(["760", "9999", "800"]), fico)
    assert normalized.tolist()[0] == 760.0
    assert pd.isna(normalized.iloc[1])
    with pytest.raises(ValueError, match="above policy maximum"):
        normalize_feature(pd.Series(["9998"]), fico)


def test_feature_policy_is_origination_only_and_semantically_scoped() -> None:
    policy = FeaturePolicy.load(POLICY)
    assert len(policy.primary_features) == 19
    assert policy.source_id_column == "loan_identifier"
    assert "postal_code" not in policy.feature_names
    assert "seller_name" not in policy.feature_names
    assert "current_loan_delinquency_status" not in policy.feature_names
    assert {item.concept for item in policy.primary_features} == {
        "borrower_creditworthiness",
        "affordability",
        "leverage",
        "loan_terms",
        "borrower_structure",
        "property_collateral",
        "geography",
        "origination_context",
    }


def test_full_synthetic_m11_m12a_m12_preparation_boundary(tmp_path: Path) -> None:
    raw = tmp_path / "historical_data_2024.zip"
    _make_raw_fixture(raw)
    m11 = tmp_path / "m11"
    target = tmp_path / "target"
    artifacts = tmp_path / "artifacts"

    intake = FreddieRawIntakeAuditor(raw).run(m11)
    assert intake.receipt.status == "PASS"
    target_builder = FreddieTargetBuilder(raw_zip=raw, protocol_path=PROTOCOL, m11_dir=m11)
    target_result = target_builder.run(target)
    assert target_result.receipt.status == "PASS"
    assert target_result.manifest["totals"]["eligible"] == 8
    assert target_result.manifest["totals"]["positive"] == 4

    adapter = FreddieMacSFLLDPreparationAdapter(
        raw_zip=raw,
        m11_dir=m11,
        target_dir=target,
        profile_path=PROFILE,
        feature_policy_path=POLICY,
        concept_registry_path=CONCEPTS,
    )
    assert adapter.validate_source()["status"] == "passed"
    result = adapter.build_canonical_bundle(artifacts)
    assert result.receipt.status == "PASS"
    assert result.manifest["rows"] == 8
    assert result.manifest["positive"] == 4
    assert result.manifest["primary_feature_count"] == 19
    assert result.manifest["performance_features_in_X"] == []

    X = pd.read_pickle(result.feature_matrix_path)
    y = pd.read_pickle(result.target_path)
    assert list(X.columns) == ["loan_identifier", *FeaturePolicy.load(POLICY).feature_names]
    assert len(X) == len(y) == 8
    assert X["loan_identifier"].is_unique
    assert y["loan_identifier"].is_unique
    # The Q1 second fixture loan intentionally uses the FICO sentinel 9999.
    assert int(X["classic_fico"].isna().sum()) == 1
    registry = pd.read_csv(artifacts / "ml/registry/feature_registry.csv")
    assert len(registry) == 19
    assert registry["concept"].isna().sum() == 0
