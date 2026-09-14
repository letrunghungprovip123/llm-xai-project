"""Freddie SFLLD 2024 preparation adapter implementation (Patch 0007 / M12B-C).

This module is the last dataset-specific boundary.  It consumes the M11 raw
intake evidence plus the M12A target partitions and emits the canonical
feature/target/semantic artifacts required by the frozen common M4-M10 path.
Monthly performance fields are never admitted to the model feature matrix.
"""
from __future__ import annotations

import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import yaml

from ..contracts import ArtifactReference, CanonicalDatasetBundle, DatasetProfile
from ..intake import evaluate_replication_profile
from ..profile import load_dataset_profile, sha256_json
from ..receipts import StageReceipt, load_receipt, sha256_path, write_json_atomic
from .raw_intake import DATASET_ID, QUARTERS, _hash_copy
from .schema import ORIGINATION_COLUMNS, PERFORMANCE_COLUMNS

PREPARATION_STAGE = "freddie_sflld_preparation"
PREPARATION_STAGE_VERSION = "v1"
PATCH_ID = "0007"
TARGET_SOURCE_COLUMN = "serious_delinquency_within_12m"


@dataclass(frozen=True)
class FeatureSpec:
    feature_name: str
    display_name: str
    description: str
    concept: str
    data_kind: str
    value_type: str
    unit: str
    normalization: Mapping[str, Any]
    direction_prior: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FeatureSpec":
        required = (
            "feature_name", "display_name", "description", "concept",
            "data_kind", "value_type", "unit", "normalization", "direction_prior",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"feature policy entry missing fields: {missing}")
        return cls(
            feature_name=str(payload["feature_name"]),
            display_name=str(payload["display_name"]),
            description=str(payload["description"]),
            concept=str(payload["concept"]),
            data_kind=str(payload["data_kind"]),
            value_type=str(payload["value_type"]),
            unit=str(payload["unit"]),
            normalization=dict(payload["normalization"]),
            direction_prior=str(payload["direction_prior"]),
        )


@dataclass(frozen=True)
class FeaturePolicy:
    dataset_id: str
    source_layout: str
    source_id_column: str
    primary_features: tuple[FeatureSpec, ...]
    excluded_features: Mapping[str, str]
    performance_feature_policy: str

    @classmethod
    def load(cls, path: Path) -> "FeaturePolicy":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "freddie_feature_policy_v1":
            raise ValueError("unsupported Freddie feature policy schema_version")
        if payload.get("dataset_id") != DATASET_ID:
            raise ValueError("feature policy dataset_id mismatch")
        specs = tuple(FeatureSpec.from_dict(item) for item in payload.get("primary_features", []))
        if not specs:
            raise ValueError("feature policy must define primary_features")
        names = [item.feature_name for item in specs]
        if len(names) != len(set(names)):
            raise ValueError("feature policy contains duplicate primary feature names")
        unknown = sorted(set(names) - set(ORIGINATION_COLUMNS))
        if unknown:
            raise ValueError(f"feature policy references unknown origination columns: {unknown}")
        if any(name in PERFORMANCE_COLUMNS for name in names if name not in ORIGINATION_COLUMNS):
            raise ValueError("performance field found in Freddie primary feature policy")
        return cls(
            dataset_id=str(payload["dataset_id"]),
            source_layout=str(payload["source_layout"]),
            source_id_column=str(payload["source_id_column"]),
            primary_features=specs,
            excluded_features=dict(payload.get("excluded_features", {})),
            performance_feature_policy=str(payload.get("performance_feature_policy", "")),
        )

    @property
    def feature_names(self) -> list[str]:
        return [item.feature_name for item in self.primary_features]


def _canonical_yaml_bytes(payload: Mapping[str, Any]) -> bytes:
    return yaml.safe_dump(
        dict(payload), sort_keys=True, allow_unicode=True, default_flow_style=False
    ).encode("utf-8")


def _write_yaml_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_bytes(_canonical_yaml_bytes(payload))
    temp.replace(path)


def _write_csv_atomic(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    frame.to_csv(temp, index=False, lineterminator="\n")
    temp.replace(path)


def _write_parquet_atomic(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.unlink(missing_ok=True)
    try:
        frame.to_parquet(temp, index=False)
    except ImportError as exc:
        raise RuntimeError(
            "A parquet engine is required for Freddie canonical artifacts. "
            "Use the project's existing pyarrow/fastparquet environment; the common M4-M10 "
            "pipeline intentionally remains parquet-based."
        ) from exc
    temp.replace(path)


def _load_concepts(path: Path) -> dict[str, dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "freddie_concept_registry_v1":
        raise ValueError("unsupported Freddie concept registry schema")
    concepts = payload.get("concepts")
    if not isinstance(concepts, dict) or not concepts:
        raise ValueError("Freddie concept registry has no concepts")
    return concepts


def _missing_mask(raw: pd.Series, tokens: list[str]) -> pd.Series:
    return raw.astype("string").str.strip().isin([str(token) for token in tokens])


def normalize_feature(raw: pd.Series, spec: FeatureSpec) -> pd.Series:
    """Normalize one raw origination column under an explicit versioned policy."""
    values = raw.astype("string").str.strip()
    rule = spec.normalization
    kind = str(rule.get("kind", ""))
    missing = _missing_mask(values, list(rule.get("missing_tokens", [])))

    if kind == "numeric":
        cleaned = values.mask(missing, pd.NA)
        numeric = pd.to_numeric(cleaned, errors="coerce")
        unexpected = cleaned.notna() & numeric.isna()
        if bool(unexpected.any()):
            examples = cleaned.loc[unexpected].drop_duplicates().head(10).tolist()
            raise ValueError(f"{spec.feature_name}: non-numeric raw tokens outside missing policy: {examples}")
        present = numeric.dropna().astype(float)
        if "min" in rule and bool((present < float(rule["min"])).any()):
            raise ValueError(f"{spec.feature_name}: values below policy minimum {rule['min']}")
        if "min_exclusive" in rule and bool((present <= float(rule["min_exclusive"])).any()):
            raise ValueError(f"{spec.feature_name}: values at/below exclusive minimum {rule['min_exclusive']}")
        if "max" in rule and bool((present > float(rule["max"])).any()):
            raise ValueError(f"{spec.feature_name}: values above policy maximum {rule['max']}")
        return numeric.astype("float64")

    if kind == "binary":
        mapping = {str(k): int(v) for k, v in dict(rule.get("mapping", {})).items()}
        cleaned = values.mask(missing, pd.NA)
        unexpected_values = sorted(set(cleaned.dropna().tolist()) - set(mapping))
        if unexpected_values:
            raise ValueError(f"{spec.feature_name}: unexpected binary values: {unexpected_values[:10]}")
        return cleaned.map(mapping).astype("float64")

    if kind == "categorical":
        allowed = {str(value) for value in rule.get("allowed_values", [])}
        cleaned = values.mask(missing, pd.NA)
        unexpected_values = sorted(set(cleaned.dropna().tolist()) - allowed)
        if unexpected_values:
            raise ValueError(f"{spec.feature_name}: unexpected categorical values: {unexpected_values[:10]}")
        return cleaned.astype("string")

    if kind == "categorical_regex":
        cleaned = values.mask(missing, pd.NA)
        pattern = re.compile(str(rule.get("regex", "")))
        invalid = cleaned.dropna().map(lambda value: pattern.fullmatch(str(value)) is None)
        if bool(invalid.any()):
            examples = cleaned.dropna().loc[invalid].drop_duplicates().head(10).tolist()
            raise ValueError(f"{spec.feature_name}: values violate regex policy: {examples}")
        return cleaned.astype("string")

    raise ValueError(f"{spec.feature_name}: unsupported normalization kind {kind!r}")


def build_feature_registry(
    frame: pd.DataFrame,
    *,
    policy: FeaturePolicy,
    concepts: Mapping[str, Mapping[str, Any]],
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for spec in policy.primary_features:
        if spec.concept not in concepts:
            raise ValueError(f"feature {spec.feature_name} references missing concept {spec.concept}")
        series = frame[spec.feature_name]
        records.append(
            {
                "feature_name": spec.feature_name,
                "display_name": spec.display_name,
                "description": spec.description,
                "concept": spec.concept,
                "concept_display_name": str(concepts[spec.concept]["display_name"]),
                "source_table": "freddie_sflld_origination",
                "source_feature_file": "orig_2024Q*.txt",
                "data_kind": spec.data_kind,
                "pandas_dtype": str(series.dtype),
                "value_type": spec.value_type,
                "unit": spec.unit,
                "missing_rate": float(series.isna().mean()),
                "non_null_count": int(series.notna().sum()),
                "unique_count": int(series.nunique(dropna=True)),
                "sensitive": False,
                "mutable": False,
                "allowed_for_model": True,
                "allowed_in_user_explanation": True,
                "allowed_in_recommendation": False,
                "direction_prior": spec.direction_prior,
                "formatting_rule": "default",
            }
        )
    registry = pd.DataFrame.from_records(records)
    if set(registry["feature_name"]) != set(policy.feature_names):
        raise ValueError("Freddie feature registry coverage mismatch")
    return registry


def _registry_yaml_payload(registry: pd.DataFrame) -> dict[str, Any]:
    features: dict[str, dict[str, Any]] = {}
    for row in registry.to_dict("records"):
        name = str(row.pop("feature_name"))
        converted = {}
        for key, value in row.items():
            if pd.isna(value):
                converted[key] = None
            elif isinstance(value, np.generic):
                converted[key] = value.item()
            else:
                converted[key] = value
        features[name] = converted
    return {"schema_version": "freddie_feature_registry_v1", "features": features}


def _artifact_reference(root: Path, path: Path) -> ArtifactReference:
    return ArtifactReference(
        path=path.relative_to(root).as_posix(),
        sha256=sha256_path(path),
        required=True,
    )


@dataclass(frozen=True)
class FreddiePreparationResult:
    bundle_path: Path
    manifest_path: Path
    receipt_path: Path
    feature_matrix_path: Path
    target_path: Path
    bundle: CanonicalDatasetBundle
    manifest: dict[str, Any]
    receipt: StageReceipt


class FreddieMacSFLLDPreparationAdapter:
    """Prepare Freddie Standard 2024 for the frozen canonical multi-dataset boundary."""

    def __init__(
        self,
        *,
        raw_zip: Path,
        m11_dir: Path,
        target_dir: Path,
        profile_path: Path,
        feature_policy_path: Path,
        concept_registry_path: Path,
    ) -> None:
        self.raw_zip = raw_zip.expanduser().resolve()
        self.m11_dir = m11_dir.expanduser().resolve()
        self.target_dir = target_dir.expanduser().resolve()
        self.profile_path = profile_path.expanduser().resolve()
        self.feature_policy_path = feature_policy_path.expanduser().resolve()
        self.concept_registry_path = concept_registry_path.expanduser().resolve()
        self.profile: DatasetProfile = load_dataset_profile(self.profile_path)
        self.policy = FeaturePolicy.load(self.feature_policy_path)
        self.concepts = _load_concepts(self.concept_registry_path)
        if self.profile.dataset_id != DATASET_ID or self.policy.dataset_id != DATASET_ID:
            raise ValueError("Freddie preparation identity mismatch")
        if self.profile.adapter.adapter_id != "freddie_sflld":
            raise ValueError("Freddie adapter requires adapter_id=freddie_sflld")
        if self.profile.entity.source_id_column != "loan_identifier":
            raise ValueError("Freddie v1 source identity must be loan_identifier")
        if self.profile.target.source_column != TARGET_SOURCE_COLUMN:
            raise ValueError("Freddie v1 source target column mismatch")
        if self.profile.capabilities.feature_count != len(self.policy.primary_features):
            raise ValueError("DatasetProfile feature_count differs from Freddie feature policy")
        missing_concepts = sorted({spec.concept for spec in self.policy.primary_features} - set(self.concepts))
        if missing_concepts:
            raise ValueError(f"feature policy concepts missing from registry: {missing_concepts}")

    def _verify_upstream(self) -> tuple[StageReceipt, StageReceipt, dict[str, Any]]:
        raw_sha = sha256_path(self.raw_zip)
        m11_receipt = load_receipt(self.m11_dir / "freddie_sflld_2024_m11_receipt_v1.json")
        if m11_receipt.stage != "freddie_sflld_raw_intake" or m11_receipt.status != "PASS":
            raise ValueError("valid M11 receipt is required")
        if m11_receipt.input_fingerprints.get("raw_source") != raw_sha:
            raise ValueError("M11 receipt raw-source fingerprint mismatch")
        for name, digest in m11_receipt.output_fingerprints.items():
            path = self.m11_dir / name
            if not path.is_file() or sha256_path(path) != digest:
                raise ValueError(f"M11 evidence missing/modified: {name}")

        target_receipt = load_receipt(
            self.target_dir / "freddie_sflld_2024_m12a_target_receipt_v1.json"
        )
        if target_receipt.stage != "freddie_sflld_target_12m" or target_receipt.status != "PASS":
            raise ValueError("valid M12A target receipt is required")
        if target_receipt.input_fingerprints.get("raw_source") != raw_sha:
            raise ValueError("M12A receipt raw-source fingerprint mismatch")
        for name, digest in target_receipt.output_fingerprints.items():
            path = self.target_dir / name
            if not path.is_file() or sha256_path(path) != digest:
                raise ValueError(f"M12A evidence missing/modified: {name}")
        target_manifest_path = self.target_dir / "freddie_target_12m_manifest_v1.json"
        target_manifest = json.loads(target_manifest_path.read_text(encoding="utf-8"))
        return m11_receipt, target_receipt, target_manifest

    def validate_source(self) -> dict[str, object]:
        try:
            m11, target, target_manifest = self._verify_upstream()
        except Exception as exc:  # surfaced as an explicit blocked preflight
            return {"status": "blocked", "error": str(exc)}
        return {
            "status": "passed",
            "dataset_id": DATASET_ID,
            "raw_source_sha256": sha256_path(self.raw_zip),
            "m11_receipt_fingerprint": m11.receipt_fingerprint,
            "m12a_receipt_fingerprint": target.receipt_fingerprint,
            "eligible_target_rows": int(target_manifest["totals"]["eligible"]),
            "primary_feature_count": len(self.policy.primary_features),
        }

    def _load_target_partition(self, quarter: str, target_manifest: Mapping[str, Any]) -> pd.DataFrame:
        partition = next(item for item in target_manifest["target_partitions"] if item["quarter"] == quarter)
        path = self.target_dir / partition["filename"]
        frame = pd.read_csv(
            path,
            dtype={"source_entity_id": "string", "target": "string", "target_observation_status": "string"},
            keep_default_na=False,
        )
        if len(frame) != int(partition["rows"]):
            raise ValueError(f"{quarter}: target partition row count mismatch")
        if frame["source_entity_id"].duplicated().any():
            raise ValueError(f"{quarter}: duplicate target source_entity_id")
        return frame

    def _load_origination_quarter(self, nested: zipfile.ZipFile, quarter: str) -> pd.DataFrame:
        use_names = ["loan_identifier", *self.policy.feature_names]
        with nested.open(f"orig_{quarter}.txt") as handle:
            # Give pandas the complete positional Release-47 schema first, then
            # select by canonical names.  Passing a short names list together
            # with non-monotonic positional usecols can silently relabel column
            # 1 as loan_identifier, which is exactly the kind of schema drift
            # this adapter is designed to prevent.
            frame = pd.read_csv(
                handle,
                sep="|",
                header=None,
                names=list(ORIGINATION_COLUMNS),
                usecols=use_names,
                dtype="string",
                na_filter=False,
            )
            frame = frame[use_names]
        if frame["loan_identifier"].duplicated().any():
            raise ValueError(f"{quarter}: duplicate origination Loan Identifier")
        return frame

    def _prepare_quarter(
        self,
        *,
        outer: zipfile.ZipFile,
        quarter: str,
        target_manifest: Mapping[str, Any],
        expected_nested_sha: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        target = self._load_target_partition(quarter, target_manifest)
        with tempfile.TemporaryDirectory(prefix=f"freddie_prepare_{quarter}_") as td:
            nested_path = Path(td) / f"{quarter}.zip"
            with outer.open(f"historical_data_{quarter}.zip") as source, nested_path.open("wb") as dest:
                nested_sha = _hash_copy(source, dest)
            if nested_sha != expected_nested_sha:
                raise ValueError(f"{quarter}: nested ZIP hash differs from M11-certified source")
            with zipfile.ZipFile(nested_path) as nested:
                orig = self._load_origination_quarter(nested, quarter)

        if set(orig["loan_identifier"].astype(str)) != set(target["source_entity_id"].astype(str)):
            raise ValueError(f"{quarter}: origination/target source identity sets differ")
        joined = orig.merge(
            target[["source_entity_id", "target", "target_observation_status"]],
            left_on="loan_identifier",
            right_on="source_entity_id",
            how="inner",
            validate="one_to_one",
        )
        if len(joined) != len(orig):
            raise ValueError(f"{quarter}: origination/target merge changed row count")
        eligible = joined.loc[joined["target_observation_status"].eq("ELIGIBLE")].copy()
        if eligible.empty:
            raise ValueError(f"{quarter}: no eligible target rows")
        if not set(eligible["target"].unique()).issubset({"0", "1"}):
            raise ValueError(f"{quarter}: eligible target contains non-binary values")

        X = pd.DataFrame({"loan_identifier": eligible["loan_identifier"].astype("string")})
        for spec in self.policy.primary_features:
            X[spec.feature_name] = normalize_feature(eligible[spec.feature_name], spec)
        y = pd.DataFrame(
            {
                "loan_identifier": eligible["loan_identifier"].astype("string"),
                TARGET_SOURCE_COLUMN: eligible["target"].astype(int),
            }
        )
        return X.reset_index(drop=True), y.reset_index(drop=True)

    def _expected_nested_hashes(self) -> dict[str, str]:
        manifest = json.loads(
            (self.m11_dir / "freddie_sflld_2024_raw_manifest_v1.json").read_text(encoding="utf-8")
        )
        return {item["quarter"]: item["nested_zip_sha256"] for item in manifest["quarters"]}

    def build_canonical_bundle(self, output_root: Path, output_path: Path | None = None) -> FreddiePreparationResult:
        m11_receipt, target_receipt, target_manifest = self._verify_upstream()
        output_root = output_root.expanduser().resolve()
        processed_dir = output_root / "data/processed"
        registry_dir = output_root / "ml/registry"
        manifest_dir = output_root / "data/manifests"
        for directory in (processed_dir, registry_dir, manifest_dir):
            directory.mkdir(parents=True, exist_ok=True)

        nested_hashes = self._expected_nested_hashes()
        feature_parts: list[pd.DataFrame] = []
        target_parts: list[pd.DataFrame] = []
        with zipfile.ZipFile(self.raw_zip) as outer:
            for quarter in QUARTERS:
                X_q, y_q = self._prepare_quarter(
                    outer=outer,
                    quarter=quarter,
                    target_manifest=target_manifest,
                    expected_nested_sha=nested_hashes[quarter],
                )
                feature_parts.append(X_q)
                target_parts.append(y_q)

        X = pd.concat(feature_parts, ignore_index=True)
        y = pd.concat(target_parts, ignore_index=True)
        if X["loan_identifier"].duplicated().any() or y["loan_identifier"].duplicated().any():
            raise ValueError("cross-quarter Freddie canonical identity collision")
        if len(X) != int(target_manifest["totals"]["eligible"]) or len(y) != len(X):
            raise ValueError("Freddie prepared row count differs from M12A eligible target count")
        if set(X["loan_identifier"].astype(str)) != set(y["loan_identifier"].astype(str)):
            raise ValueError("Freddie feature/target identity sets differ")
        if int(y[TARGET_SOURCE_COLUMN].sum()) != int(target_manifest["totals"]["positive"]):
            raise ValueError("Freddie prepared positive count differs from M12A")
        forbidden_overlap = sorted(set(X.columns) & set(PERFORMANCE_COLUMNS))
        # loan_identifier exists in both layouts by design as identity, not a model feature.
        forbidden_overlap = [name for name in forbidden_overlap if name != "loan_identifier"]
        if forbidden_overlap:
            raise ValueError(f"performance leakage columns reached feature matrix: {forbidden_overlap}")
        expected_columns = ["loan_identifier", *self.policy.feature_names]
        if list(X.columns) != expected_columns:
            raise ValueError("Freddie feature matrix column order differs from versioned primary policy")

        registry = build_feature_registry(X, policy=self.policy, concepts=self.concepts)
        feature_matrix_path = processed_dir / "feature_matrix_full.parquet"
        target_path = processed_dir / "target_full.parquet"
        registry_csv_path = registry_dir / "feature_registry.csv"
        registry_yaml_path = registry_dir / "feature_registry.yaml"
        concept_yaml_path = registry_dir / "concept_registry.yaml"
        _write_parquet_atomic(feature_matrix_path, X)
        _write_parquet_atomic(target_path, y)
        _write_csv_atomic(registry_csv_path, registry)
        _write_yaml_atomic(registry_yaml_path, _registry_yaml_payload(registry))
        concept_payload = yaml.safe_load(self.concept_registry_path.read_text(encoding="utf-8"))
        _write_yaml_atomic(concept_yaml_path, concept_payload)

        raw_sha = sha256_path(self.raw_zip)
        policy_sha = sha256_path(self.feature_policy_path)
        concepts_sha = sha256_path(self.concept_registry_path)
        target_protocol_sha = str(target_manifest["target_protocol_sha256"])
        adapter_code_sha = sha256_path(Path(__file__).resolve())
        profile_sha = sha256_json(self.profile.to_dict())
        fingerprint_payload = {
            "schema_version": "freddie_dataset_fingerprint_v1",
            "dataset_id": self.profile.dataset_id,
            "dataset_version": self.profile.dataset_version,
            "raw_source_sha256": raw_sha,
            "target_protocol_sha256": target_protocol_sha,
            "feature_policy_sha256": policy_sha,
            "concept_registry_sha256": concepts_sha,
            "adapter_code_sha256": adapter_code_sha,
        }
        dataset_fingerprint = sha256_json(fingerprint_payload)

        references = {
            "feature_matrix": _artifact_reference(output_root, feature_matrix_path),
            "target": _artifact_reference(output_root, target_path),
            "feature_registry_csv": _artifact_reference(output_root, registry_csv_path),
            "feature_registry_yaml": _artifact_reference(output_root, registry_yaml_path),
            "concept_registry_yaml": _artifact_reference(output_root, concept_yaml_path),
        }
        bundle = CanonicalDatasetBundle(
            schema_version="canonical_dataset_bundle_v1",
            dataset_id=self.profile.dataset_id,
            dataset_version=self.profile.dataset_version,
            dataset_fingerprint=dataset_fingerprint,
            dataset_profile_sha256=profile_sha,
            artifacts=references,
            provenance={
                "adapter_id": self.profile.adapter.adapter_id,
                "adapter_version": self.profile.adapter.adapter_version,
                "fingerprint_method": "raw_target_feature_semantics_adapter_hash_v1",
                "artifact_source_root_locator": str(output_root),
                "artifact_paths_relative_to_source_root": True,
                "raw_source_sha256": raw_sha,
                "m11_receipt_fingerprint": m11_receipt.receipt_fingerprint,
                "m12a_target_receipt_fingerprint": target_receipt.receipt_fingerprint,
            },
        )
        bundle_path = output_path or manifest_dir / "canonical_dataset_bundle_freddie_sflld_2024_v1.json"
        write_json_atomic(bundle_path, bundle.to_dict())

        audit = {
            "schema_version": "freddie_preparation_manifest_v1",
            "dataset_id": DATASET_ID,
            "dataset_version": self.profile.dataset_version,
            "dataset_fingerprint": dataset_fingerprint,
            "raw_source_sha256": raw_sha,
            "rows": int(len(X)),
            "positive": int(y[TARGET_SOURCE_COLUMN].sum()),
            "negative": int((y[TARGET_SOURCE_COLUMN] == 0).sum()),
            "primary_feature_count": len(self.policy.primary_features),
            "primary_features": self.policy.feature_names,
            "excluded_features": dict(self.policy.excluded_features),
            "performance_feature_policy": self.policy.performance_feature_policy,
            "performance_features_in_X": forbidden_overlap,
            "feature_statistics": {
                row["feature_name"]: {
                    "missing_rate": float(row["missing_rate"]),
                    "non_null_count": int(row["non_null_count"]),
                    "unique_count": int(row["unique_count"]),
                    "concept": row["concept"],
                    "data_kind": row["data_kind"],
                }
                for row in registry.to_dict("records")
            },
            "fingerprint_inputs": fingerprint_payload,
            "artifacts": {name: ref.to_dict() for name, ref in references.items()},
            "invariants": {
                "upstream_receipts_verified": "PASS",
                "eligible_target_only": "PASS",
                "feature_target_identity_match": "PASS",
                "unique_source_entity_id": "PASS",
                "performance_leakage_absent": "PASS",
                "feature_policy_exact": "PASS",
                "semantic_registry_complete": "PASS",
                "target_count_matches_m12a": "PASS",
            },
        }
        manifest_path = manifest_dir / "freddie_sflld_2024_preparation_manifest_v1.json"
        write_json_atomic(manifest_path, audit)

        profile_report = evaluate_replication_profile(self.profile, bundle)
        if profile_report.failures:
            raise ValueError(
                "Freddie canonical profile gate failed: "
                + "; ".join(f"{item.check_id}: {item.detail}" for item in profile_report.failures)
            )
        profile_report_path = manifest_dir / "freddie_sflld_2024_replication_profile_report_v1.json"
        write_json_atomic(profile_report_path, profile_report.to_dict())

        output_fingerprints = {
            **{path.name: sha256_path(path) for path in (
                feature_matrix_path, target_path, registry_csv_path, registry_yaml_path,
                concept_yaml_path, bundle_path, manifest_path, profile_report_path,
            )}
        }
        receipt = StageReceipt(
            stage=PREPARATION_STAGE,
            stage_version=PREPARATION_STAGE_VERSION,
            dataset_id=DATASET_ID,
            patch_id=PATCH_ID,
            input_fingerprints={
                "raw_source": raw_sha,
                "m11_receipt": sha256_path(self.m11_dir / "freddie_sflld_2024_m11_receipt_v1.json"),
                "m12a_target_receipt": sha256_path(
                    self.target_dir / "freddie_sflld_2024_m12a_target_receipt_v1.json"
                ),
            },
            config_fingerprints={
                "dataset_profile": sha256_path(self.profile_path),
                "feature_policy": policy_sha,
                "concept_registry": concepts_sha,
                "target_protocol": target_protocol_sha,
                "adapter_code": adapter_code_sha,
            },
            output_fingerprints=output_fingerprints,
            invariants=audit["invariants"],
        )
        receipt_path = manifest_dir / "freddie_sflld_2024_m12_preparation_receipt_v1.json"
        write_json_atomic(receipt_path, receipt.to_dict())
        return FreddiePreparationResult(
            bundle_path=bundle_path,
            manifest_path=manifest_path,
            receipt_path=receipt_path,
            feature_matrix_path=feature_matrix_path,
            target_path=target_path,
            bundle=bundle,
            manifest=audit,
            receipt=receipt,
        )
