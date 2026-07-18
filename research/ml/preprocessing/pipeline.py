
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any

import joblib
import numpy as np
import pandas as pd

from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder


PROJECT_ROOT = Path(__file__).resolve().parents[3]

SPLIT_DIR = PROJECT_ROOT / "data" / "processed" / "splits"

TREE_DIR = PROJECT_ROOT / "data" / "processed" / "model_ready" / "tree"
LINEAR_DIR = PROJECT_ROOT / "data" / "processed" / "model_ready" / "linear"

REPORT_DIR = PROJECT_ROOT / "data" / "reports"
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"
REGISTRY_DIR = PROJECT_ROOT / "ml" / "registry"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts" / "preprocessing"

TREE_DIR.mkdir(parents=True, exist_ok=True)
LINEAR_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

X_TRAIN_PATH = SPLIT_DIR / "X_train.parquet"
Y_TRAIN_PATH = SPLIT_DIR / "y_train.parquet"
X_VALID_PATH = SPLIT_DIR / "X_valid.parquet"
Y_VALID_PATH = SPLIT_DIR / "y_valid.parquet"
X_TEST_PATH = SPLIT_DIR / "X_test.parquet"
Y_TEST_PATH = SPLIT_DIR / "y_test.parquet"

MODEL_FEATURE_COLUMNS_PATH = REGISTRY_DIR / "model_feature_columns.json"
MODEL_FEATURE_METADATA_PATH = REGISTRY_DIR / "model_feature_metadata.json"
ID_COLUMNS_PATH = REGISTRY_DIR / "id_columns.json"
TARGET_COLUMN_PATH = REGISTRY_DIR / "target_column.json"
FEATURE_REGISTRY_CSV_PATH = REGISTRY_DIR / "feature_registry.csv"

RANDOM_STATE = 42
RARE_CATEGORY_THRESHOLD = 0.01

MISSING_CATEGORY_TOKEN = "__MISSING__"
RARE_CATEGORY_TOKEN = "__RARE__"
UNKNOWN_CATEGORY_TOKEN = "__UNKNOWN__"

TREE_PREPROCESSOR_PATH = ARTIFACT_DIR / "tree_preprocessor.joblib"
LINEAR_PREPROCESSOR_PATH = ARTIFACT_DIR / "linear_preprocessor.joblib"

PREPROCESSED_FEATURE_COLUMNS_TREE_PATH = REGISTRY_DIR / "preprocessed_feature_columns_tree.json"
PREPROCESSED_FEATURE_COLUMNS_LINEAR_PATH = REGISTRY_DIR / "preprocessed_feature_columns_linear.json"

PREPROCESSED_FEATURE_MAPPING_TREE_PATH = REGISTRY_DIR / "preprocessed_feature_mapping_tree.json"
PREPROCESSED_FEATURE_MAPPING_LINEAR_PATH = REGISTRY_DIR / "preprocessed_feature_mapping_linear.json"

PREPROCESSING_MANIFEST_PATH = MANIFEST_DIR / "preprocessing_manifest.json"
BATCH_E_SUMMARY_MANIFEST_PATH = MANIFEST_DIR / "batch_e_preprocessing_summary.json"

PREPROCESSING_REPORT_PATH = REPORT_DIR / "preprocessing_report.md"
BATCH_E_SUMMARY_REPORT_PATH = REPORT_DIR / "batch_e_preprocessing_summary.md"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(data: Any, path: Path) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def ensure_inputs_exist() -> None:
    required_files = [
        X_TRAIN_PATH,
        Y_TRAIN_PATH,
        X_VALID_PATH,
        Y_VALID_PATH,
        X_TEST_PATH,
        Y_TEST_PATH,
        MODEL_FEATURE_COLUMNS_PATH,
        FEATURE_REGISTRY_CSV_PATH,
    ]

    missing = [
        relative(path)
        for path in required_files
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(f"Missing required Batch E input files: {missing}")


def load_model_feature_columns() -> list[str]:
    data = read_json(MODEL_FEATURE_COLUMNS_PATH)

    if isinstance(data, list):
        columns = data
    elif isinstance(data, dict):
        columns = None
        for key in [
            "model_feature_columns",
            "features",
            "columns",
            "feature_columns",
        ]:
            if key in data and isinstance(data[key], list):
                columns = data[key]
                break

        if columns is None:
            raise ValueError(
                f"Cannot find model feature columns list in {relative(MODEL_FEATURE_COLUMNS_PATH)}"
            )
    else:
        raise ValueError("model_feature_columns.json must be a list or dict")

    columns = [str(c) for c in columns]

    if "SK_ID_CURR" in columns:
        columns = [c for c in columns if c != "SK_ID_CURR"]

    if "TARGET" in columns:
        raise ValueError("TARGET appears in model_feature_columns.json")

    duplicate_columns = sorted(
        [
            col
            for col in set(columns)
            if columns.count(col) > 1
        ]
    )

    if duplicate_columns:
        raise ValueError(f"Duplicate model feature columns found: {duplicate_columns[:50]}")

    return columns


def load_id_columns() -> list[str]:
    if not ID_COLUMNS_PATH.exists():
        return ["SK_ID_CURR"]

    data = read_json(ID_COLUMNS_PATH)

    if isinstance(data, list):
        return [str(c) for c in data]

    if isinstance(data, dict):
        for key in ["id_columns", "ids", "columns"]:
            if key in data and isinstance(data[key], list):
                return [str(c) for c in data[key]]

    return ["SK_ID_CURR"]


def load_target_column() -> str:
    if not TARGET_COLUMN_PATH.exists():
        return "TARGET"

    data = read_json(TARGET_COLUMN_PATH)

    if isinstance(data, str):
        return data

    if isinstance(data, dict):
        for key in ["target_column", "target", "column"]:
            if key in data:
                return str(data[key])

    return "TARGET"


def load_feature_metadata() -> dict[str, dict[str, Any]]:
    if not FEATURE_REGISTRY_CSV_PATH.exists():
        raise FileNotFoundError(
            f"Missing feature registry: {relative(FEATURE_REGISTRY_CSV_PATH)}"
        )

    df = pd.read_csv(FEATURE_REGISTRY_CSV_PATH)

    if "feature_name" not in df.columns:
        raise ValueError("feature_registry.csv is missing feature_name column")

    metadata: dict[str, dict[str, Any]] = {}

    for _, row in df.iterrows():
        feature_name = str(row["feature_name"])

        item: dict[str, Any] = {}
        for col in df.columns:
            value = row[col]
            if pd.isna(value):
                item[col] = None
            elif isinstance(value, np.generic):
                item[col] = value.item()
            else:
                item[col] = value

        metadata[feature_name] = item

    return metadata


def load_split_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    print("[Batch E] Loading split parquet files ...")

    X_train = pd.read_parquet(X_TRAIN_PATH)
    y_train = pd.read_parquet(Y_TRAIN_PATH)

    X_valid = pd.read_parquet(X_VALID_PATH)
    y_valid = pd.read_parquet(Y_VALID_PATH)

    X_test = pd.read_parquet(X_TEST_PATH)
    y_test = pd.read_parquet(Y_TEST_PATH)

    return X_train, y_train, X_valid, y_valid, X_test, y_test


def count_missing(df: pd.DataFrame) -> int:
    return int(df.isna().sum().sum())


def count_inf(df: pd.DataFrame) -> int:
    numeric_df = df.select_dtypes(include=[np.number])

    if numeric_df.empty:
        return 0

    return int(np.isinf(numeric_df.to_numpy()).sum())


def validate_raw_split_inputs(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_valid: pd.DataFrame,
    y_valid: pd.DataFrame,
    X_test: pd.DataFrame,
    y_test: pd.DataFrame,
    model_feature_columns: list[str],
    id_columns: list[str],
    target_column: str,
    feature_metadata: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    errors = []
    warnings = []

    split_pairs = {
        "train": (X_train, y_train),
        "valid": (X_valid, y_valid),
        "test": (X_test, y_test),
    }

    for split_name, (X_part, y_part) in split_pairs.items():
        if "SK_ID_CURR" not in X_part.columns:
            errors.append(f"{split_name}: X missing SK_ID_CURR")

        if "SK_ID_CURR" not in y_part.columns:
            errors.append(f"{split_name}: y missing SK_ID_CURR")

        if target_column not in y_part.columns:
            errors.append(f"{split_name}: y missing target column {target_column}")

        if target_column in X_part.columns:
            errors.append(f"{split_name}: target column found in X")

        duplicate_x_ids = (
            int(X_part["SK_ID_CURR"].duplicated().sum())
            if "SK_ID_CURR" in X_part.columns
            else None
        )

        duplicate_y_ids = (
            int(y_part["SK_ID_CURR"].duplicated().sum())
            if "SK_ID_CURR" in y_part.columns
            else None
        )

        if duplicate_x_ids and duplicate_x_ids > 0:
            errors.append(f"{split_name}: duplicate SK_ID_CURR in X: {duplicate_x_ids}")

        if duplicate_y_ids and duplicate_y_ids > 0:
            errors.append(f"{split_name}: duplicate SK_ID_CURR in y: {duplicate_y_ids}")

        if len(X_part) != len(y_part):
            errors.append(f"{split_name}: X/y row mismatch: X={len(X_part)}, y={len(y_part)}")

        if "SK_ID_CURR" in X_part.columns and "SK_ID_CURR" in y_part.columns:
            if set(X_part["SK_ID_CURR"].tolist()) != set(y_part["SK_ID_CURR"].tolist()):
                errors.append(f"{split_name}: X/y SK_ID_CURR sets do not match")

    base_columns = list(X_train.columns)

    for split_name, X_part in {
        "valid": X_valid,
        "test": X_test,
    }.items():
        if list(X_part.columns) != base_columns:
            errors.append(f"{split_name}: X columns differ from train X columns")

    missing_model_features = [
        c for c in model_feature_columns
        if c not in X_train.columns
    ]

    if missing_model_features:
        errors.append(f"model features missing in X_train: {missing_model_features[:50]}")

    missing_metadata_features = [
        c for c in model_feature_columns
        if c not in feature_metadata
    ]

    if missing_metadata_features:
        warnings.append(f"model features missing in feature_registry.csv: {missing_metadata_features[:50]}")

    extra_candidate_features = [
        c for c in X_train.columns
        if c not in model_feature_columns and c not in id_columns
    ]

    if extra_candidate_features:
        warnings.append(f"extra X columns not in model_feature_columns: {extra_candidate_features[:50]}")

    forbidden_for_model = [
        c for c in model_feature_columns
        if c in id_columns or c == target_column
    ]

    if forbidden_for_model:
        errors.append(f"forbidden columns inside model_feature_columns: {forbidden_for_model}")

    duplicate_model_features = sorted(
        [
            col
            for col in set(model_feature_columns)
            if model_feature_columns.count(col) > 1
        ]
    )

    if duplicate_model_features:
        errors.append(f"duplicate model feature columns: {duplicate_model_features[:50]}")

    return {
        "train_rows": int(len(X_train)),
        "valid_rows": int(len(X_valid)),
        "test_rows": int(len(X_test)),
        "model_feature_count": int(len(model_feature_columns)),
        "id_columns": id_columns,
        "target_column": target_column,
        "missing_model_features": missing_model_features[:100],
        "missing_metadata_features": missing_metadata_features[:100],
        "extra_candidate_features": extra_candidate_features[:100],
        "warning_count": len(warnings),
        "warnings": warnings,
        "error_count": len(errors),
        "errors": errors,
        "status": "passed" if not errors else "blocked",
    }


def infer_feature_groups(
    X_train: pd.DataFrame,
    model_feature_columns: list[str],
    feature_metadata: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    categorical_features = []
    binary_features = []
    numeric_features = []

    for feature in model_feature_columns:
        meta = feature_metadata.get(feature, {})
        data_kind = str(meta.get("data_kind", "")).lower()
        value_type = str(meta.get("value_type", "")).lower()

        if data_kind == "categorical" or value_type == "categorical":
            categorical_features.append(feature)
            continue

        if data_kind == "binary" or value_type == "binary_indicator":
            binary_features.append(feature)
            continue

        if feature.startswith("has_") or feature.endswith("_flag") or feature.endswith("_abnormal"):
            binary_features.append(feature)
            continue

        if not pd.api.types.is_numeric_dtype(X_train[feature]):
            categorical_features.append(feature)
            continue

        numeric_features.append(feature)

    categorical_features = list(dict.fromkeys(categorical_features))
    binary_features = list(dict.fromkeys(binary_features))
    numeric_features = list(dict.fromkeys(numeric_features))

    cat_set = set(categorical_features)
    bin_set = set(binary_features)

    numeric_features = [
        c for c in numeric_features
        if c not in cat_set and c not in bin_set
    ]

    assigned = set(numeric_features) | set(binary_features) | set(categorical_features)
    unassigned = [
        c for c in model_feature_columns
        if c not in assigned
    ]

    if unassigned:
        raise ValueError(f"Unassigned features found during preprocessing grouping: {unassigned[:50]}")

    return {
        "numeric_features": numeric_features,
        "categorical_features": categorical_features,
        "binary_features": binary_features,
    }


def fit_rare_category_mapping(
    X_train: pd.DataFrame,
    categorical_features: list[str],
    rare_threshold: float,
) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}

    for feature in categorical_features:
        series = (
            X_train[feature]
            .fillna(MISSING_CATEGORY_TOKEN)
            .astype(str)
        )

        freq = series.value_counts(normalize=True, dropna=False)

        kept_categories = sorted(
            [
                str(cat)
                for cat, rate in freq.items()
                if rate >= rare_threshold
            ]
        )

        rare_categories = sorted(
            [
                str(cat)
                for cat, rate in freq.items()
                if rate < rare_threshold
            ]
        )

        for token in [
            MISSING_CATEGORY_TOKEN,
            RARE_CATEGORY_TOKEN,
            UNKNOWN_CATEGORY_TOKEN,
        ]:
            if token not in kept_categories:
                kept_categories.append(token)

        mapping[feature] = {
            "rare_threshold": rare_threshold,
            "kept_categories": kept_categories,
            "rare_categories": rare_categories,
            "train_unique_count": int(series.nunique(dropna=False)),
            "kept_category_count": int(len(kept_categories)),
            "rare_category_count": int(len(rare_categories)),
        }

    return mapping


def apply_rare_category_mapping(
    X: pd.DataFrame,
    categorical_features: list[str],
    rare_mapping: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    out = pd.DataFrame(index=X.index)

    for feature in categorical_features:
        series = (
            X[feature]
            .fillna(MISSING_CATEGORY_TOKEN)
            .astype(str)
        )

        kept_categories = set(rare_mapping[feature]["kept_categories"])
        rare_categories = set(rare_mapping[feature]["rare_categories"])

        def map_value(value: str) -> str:
            if value == MISSING_CATEGORY_TOKEN:
                return MISSING_CATEGORY_TOKEN

            if value in rare_categories:
                return RARE_CATEGORY_TOKEN

            if value in kept_categories:
                return value

            return UNKNOWN_CATEGORY_TOKEN

        out[feature] = series.map(map_value)

    return out


def create_one_hot_encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(
            handle_unknown="ignore",
            sparse_output=False,
            dtype=np.float32,
        )
    except TypeError:
        return OneHotEncoder(
            handle_unknown="ignore",
            sparse=False,
            dtype=np.float32,
        )


def sanitize_feature_part(value: str) -> str:
    value = str(value)
    replacements = {
        " ": "_",
        "/": "_",
        "\\": "_",
        "-": "_",
        ":": "_",
        ",": "_",
        ";": "_",
        "|": "_",
        ".": "_",
        "(": "",
        ")": "",
        "[": "",
        "]": "",
        "{": "",
        "}": "",
        "'": "",
        '"': "",
    }

    for src, dst in replacements.items():
        value = value.replace(src, dst)

    while "__" in value:
        value = value.replace("__", "_")

    return value.strip("_")


def build_one_hot_feature_names(
    encoder: OneHotEncoder,
    categorical_features: list[str],
) -> list[str]:
    output_names = []

    categories = encoder.categories_

    for feature, cats in zip(categorical_features, categories):
        for cat in cats:
            safe_cat = sanitize_feature_part(str(cat))
            output_names.append(f"{feature}__{safe_cat}")

    duplicate_names = sorted(
        [
            name
            for name in set(output_names)
            if output_names.count(name) > 1
        ]
    )

    if duplicate_names:
        raise ValueError(f"Duplicate one-hot feature names found: {duplicate_names[:50]}")

    return output_names


def transform_numeric(
    X_train: pd.DataFrame,
    X_valid: pd.DataFrame,
    X_test: pd.DataFrame,
    numeric_features: list[str],
    scaled: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if not numeric_features:
        empty_train = pd.DataFrame(index=X_train.index)
        empty_valid = pd.DataFrame(index=X_valid.index)
        empty_test = pd.DataFrame(index=X_test.index)

        return empty_train, empty_valid, empty_test, {
            "numeric_imputer": None,
            "numeric_scaler": None,
            "numeric_features": [],
            "scaled": scaled,
        }

    imputer = SimpleImputer(strategy="median")

    train_imputed = imputer.fit_transform(X_train[numeric_features])
    valid_imputed = imputer.transform(X_valid[numeric_features])
    test_imputed = imputer.transform(X_test[numeric_features])

    scaler = None

    if scaled:
        scaler = StandardScaler()
        train_values = scaler.fit_transform(train_imputed)
        valid_values = scaler.transform(valid_imputed)
        test_values = scaler.transform(test_imputed)
    else:
        train_values = train_imputed
        valid_values = valid_imputed
        test_values = test_imputed

    train_df = pd.DataFrame(
        train_values.astype(np.float32),
        columns=numeric_features,
        index=X_train.index,
    )

    valid_df = pd.DataFrame(
        valid_values.astype(np.float32),
        columns=numeric_features,
        index=X_valid.index,
    )

    test_df = pd.DataFrame(
        test_values.astype(np.float32),
        columns=numeric_features,
        index=X_test.index,
    )

    artifact = {
        "numeric_imputer": imputer,
        "numeric_scaler": scaler,
        "numeric_features": numeric_features,
        "scaled": scaled,
    }

    return train_df, valid_df, test_df, artifact


def transform_binary(
    X_train: pd.DataFrame,
    X_valid: pd.DataFrame,
    X_test: pd.DataFrame,
    binary_features: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if not binary_features:
        empty_train = pd.DataFrame(index=X_train.index)
        empty_valid = pd.DataFrame(index=X_valid.index)
        empty_test = pd.DataFrame(index=X_test.index)

        return empty_train, empty_valid, empty_test, {
            "binary_imputer": None,
            "binary_features": [],
        }

    imputer = SimpleImputer(strategy="most_frequent")

    train_values = imputer.fit_transform(X_train[binary_features])
    valid_values = imputer.transform(X_valid[binary_features])
    test_values = imputer.transform(X_test[binary_features])

    train_df = pd.DataFrame(
        train_values.astype(np.float32),
        columns=binary_features,
        index=X_train.index,
    )

    valid_df = pd.DataFrame(
        valid_values.astype(np.float32),
        columns=binary_features,
        index=X_valid.index,
    )

    test_df = pd.DataFrame(
        test_values.astype(np.float32),
        columns=binary_features,
        index=X_test.index,
    )

    artifact = {
        "binary_imputer": imputer,
        "binary_features": binary_features,
    }

    return train_df, valid_df, test_df, artifact


def transform_categorical(
    X_train: pd.DataFrame,
    X_valid: pd.DataFrame,
    X_test: pd.DataFrame,
    categorical_features: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], list[str]]:
    if not categorical_features:
        empty_train = pd.DataFrame(index=X_train.index)
        empty_valid = pd.DataFrame(index=X_valid.index)
        empty_test = pd.DataFrame(index=X_test.index)

        return empty_train, empty_valid, empty_test, {
            "categorical_features": [],
            "rare_mapping": {},
            "one_hot_encoder": None,
        }, []

    rare_mapping = fit_rare_category_mapping(
        X_train=X_train,
        categorical_features=categorical_features,
        rare_threshold=RARE_CATEGORY_THRESHOLD,
    )

    train_cat = apply_rare_category_mapping(
        X=X_train,
        categorical_features=categorical_features,
        rare_mapping=rare_mapping,
    )

    valid_cat = apply_rare_category_mapping(
        X=X_valid,
        categorical_features=categorical_features,
        rare_mapping=rare_mapping,
    )

    test_cat = apply_rare_category_mapping(
        X=X_test,
        categorical_features=categorical_features,
        rare_mapping=rare_mapping,
    )

    encoder = create_one_hot_encoder()

    train_values = encoder.fit_transform(train_cat[categorical_features])
    valid_values = encoder.transform(valid_cat[categorical_features])
    test_values = encoder.transform(test_cat[categorical_features])

    one_hot_feature_names = build_one_hot_feature_names(
        encoder=encoder,
        categorical_features=categorical_features,
    )

    train_df = pd.DataFrame(
        train_values.astype(np.float32),
        columns=one_hot_feature_names,
        index=X_train.index,
    )

    valid_df = pd.DataFrame(
        valid_values.astype(np.float32),
        columns=one_hot_feature_names,
        index=X_valid.index,
    )

    test_df = pd.DataFrame(
        test_values.astype(np.float32),
        columns=one_hot_feature_names,
        index=X_test.index,
    )

    artifact = {
        "categorical_features": categorical_features,
        "rare_category_threshold": RARE_CATEGORY_THRESHOLD,
        "missing_category_token": MISSING_CATEGORY_TOKEN,
        "rare_category_token": RARE_CATEGORY_TOKEN,
        "unknown_category_token": UNKNOWN_CATEGORY_TOKEN,
        "rare_mapping": rare_mapping,
        "one_hot_encoder": encoder,
        "one_hot_feature_names": one_hot_feature_names,
    }

    return train_df, valid_df, test_df, artifact, one_hot_feature_names


def build_preprocessed_feature_mapping(
    numeric_features: list[str],
    binary_features: list[str],
    categorical_features: list[str],
    one_hot_feature_names: list[str],
    feature_metadata: dict[str, dict[str, Any]],
    pipeline_type: str,
) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}

    for feature in numeric_features:
        meta = feature_metadata.get(feature, {})

        mapping[feature] = {
            "preprocessed_feature": feature,
            "original_feature": feature,
            "encoded_from": "numeric_scaled" if pipeline_type == "linear" else "numeric_imputed",
            "pipeline_type": pipeline_type,
            "concept": meta.get("concept"),
            "concept_display_name": meta.get("concept_display_name"),
            "value_type": meta.get("value_type"),
            "unit": meta.get("unit"),
            "display_name": meta.get("display_name", feature),
            "allowed_in_user_explanation": meta.get("allowed_in_user_explanation"),
            "sensitive": meta.get("sensitive"),
            "direction_prior": meta.get("direction_prior"),
        }

    for feature in binary_features:
        meta = feature_metadata.get(feature, {})

        mapping[feature] = {
            "preprocessed_feature": feature,
            "original_feature": feature,
            "encoded_from": "binary_imputed",
            "pipeline_type": pipeline_type,
            "concept": meta.get("concept"),
            "concept_display_name": meta.get("concept_display_name"),
            "value_type": meta.get("value_type"),
            "unit": meta.get("unit"),
            "display_name": meta.get("display_name", feature),
            "allowed_in_user_explanation": meta.get("allowed_in_user_explanation"),
            "sensitive": meta.get("sensitive"),
            "direction_prior": meta.get("direction_prior"),
        }

    for encoded_feature in one_hot_feature_names:
        original_feature = None
        encoded_category = None

        for cat_feature in categorical_features:
            prefix = f"{cat_feature}__"
            if encoded_feature.startswith(prefix):
                original_feature = cat_feature
                encoded_category = encoded_feature[len(prefix):]
                break

        if original_feature is None:
            original_feature = encoded_feature.split("__")[0]

        meta = feature_metadata.get(original_feature, {})

        mapping[encoded_feature] = {
            "preprocessed_feature": encoded_feature,
            "original_feature": original_feature,
            "encoded_category": encoded_category,
            "encoded_from": "one_hot",
            "pipeline_type": pipeline_type,
            "concept": meta.get("concept"),
            "concept_display_name": meta.get("concept_display_name"),
            "value_type": meta.get("value_type", "categorical"),
            "unit": meta.get("unit"),
            "display_name": meta.get("display_name", original_feature),
            "allowed_in_user_explanation": meta.get("allowed_in_user_explanation"),
            "sensitive": meta.get("sensitive"),
            "direction_prior": meta.get("direction_prior"),
        }

    return mapping


def build_model_ready_dataset(
    X_train: pd.DataFrame,
    X_valid: pd.DataFrame,
    X_test: pd.DataFrame,
    numeric_features: list[str],
    categorical_features: list[str],
    binary_features: list[str],
    feature_metadata: dict[str, dict[str, Any]],
    pipeline_type: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, dict[str, Any]]]:
    scaled = pipeline_type == "linear"

    print(f"[Batch E] Building {pipeline_type} model-ready dataset ...")

    numeric_train, numeric_valid, numeric_test, numeric_artifact = transform_numeric(
        X_train=X_train,
        X_valid=X_valid,
        X_test=X_test,
        numeric_features=numeric_features,
        scaled=scaled,
    )

    binary_train, binary_valid, binary_test, binary_artifact = transform_binary(
        X_train=X_train,
        X_valid=X_valid,
        X_test=X_test,
        binary_features=binary_features,
    )

    cat_train, cat_valid, cat_test, categorical_artifact, one_hot_feature_names = transform_categorical(
        X_train=X_train,
        X_valid=X_valid,
        X_test=X_test,
        categorical_features=categorical_features,
    )

    X_train_ready = pd.concat(
        [numeric_train, binary_train, cat_train],
        axis=1,
    ).reset_index(drop=True)

    X_valid_ready = pd.concat(
        [numeric_valid, binary_valid, cat_valid],
        axis=1,
    ).reset_index(drop=True)

    X_test_ready = pd.concat(
        [numeric_test, binary_test, cat_test],
        axis=1,
    ).reset_index(drop=True)

    preprocessed_columns = list(X_train_ready.columns)

    feature_mapping = build_preprocessed_feature_mapping(
        numeric_features=numeric_features,
        binary_features=binary_features,
        categorical_features=categorical_features,
        one_hot_feature_names=one_hot_feature_names,
        feature_metadata=feature_metadata,
        pipeline_type=pipeline_type,
    )

    artifact = {
        "pipeline_type": pipeline_type,
        "created_at": now_iso(),
        "random_state": RANDOM_STATE,
        "input_feature_groups": {
            "numeric_features": numeric_features,
            "binary_features": binary_features,
            "categorical_features": categorical_features,
        },
        "numeric_artifact": numeric_artifact,
        "binary_artifact": binary_artifact,
        "categorical_artifact": categorical_artifact,
        "preprocessed_feature_columns": preprocessed_columns,
        "preprocessed_feature_mapping": feature_mapping,
    }

    return X_train_ready, X_valid_ready, X_test_ready, artifact, feature_mapping


def validate_model_ready_dataset(
    X_train_ready: pd.DataFrame,
    X_valid_ready: pd.DataFrame,
    X_test_ready: pd.DataFrame,
    pipeline_type: str,
) -> dict[str, Any]:
    errors = []

    if list(X_train_ready.columns) != list(X_valid_ready.columns):
        errors.append(f"{pipeline_type}: valid columns differ from train columns")

    if list(X_train_ready.columns) != list(X_test_ready.columns):
        errors.append(f"{pipeline_type}: test columns differ from train columns")

    duplicate_columns = sorted(
        [
            col
            for col in set(X_train_ready.columns)
            if list(X_train_ready.columns).count(col) > 1
        ]
    )

    if duplicate_columns:
        errors.append(f"{pipeline_type}: duplicate preprocessed columns: {duplicate_columns[:50]}")

    for split_name, df in {
        "train": X_train_ready,
        "valid": X_valid_ready,
        "test": X_test_ready,
    }.items():
        if "SK_ID_CURR" in df.columns:
            errors.append(f"{pipeline_type}/{split_name}: SK_ID_CURR found in model-ready matrix")

        if "TARGET" in df.columns:
            errors.append(f"{pipeline_type}/{split_name}: TARGET found in model-ready matrix")

        missing_count = count_missing(df)
        inf_count = count_inf(df)
        object_columns = df.select_dtypes(include=["object", "string", "category"]).columns.tolist()

        if missing_count > 0:
            errors.append(f"{pipeline_type}/{split_name}: missing values remain: {missing_count}")

        if inf_count > 0:
            errors.append(f"{pipeline_type}/{split_name}: inf/-inf values remain: {inf_count}")

        if object_columns:
            errors.append(f"{pipeline_type}/{split_name}: object/string columns remain: {object_columns[:30]}")

    return {
        "pipeline_type": pipeline_type,
        "train_shape": [int(X_train_ready.shape[0]), int(X_train_ready.shape[1])],
        "valid_shape": [int(X_valid_ready.shape[0]), int(X_valid_ready.shape[1])],
        "test_shape": [int(X_test_ready.shape[0]), int(X_test_ready.shape[1])],
        "preprocessed_feature_count": int(X_train_ready.shape[1]),
        "train_missing_count": count_missing(X_train_ready),
        "valid_missing_count": count_missing(X_valid_ready),
        "test_missing_count": count_missing(X_test_ready),
        "train_inf_count": count_inf(X_train_ready),
        "valid_inf_count": count_inf(X_valid_ready),
        "test_inf_count": count_inf(X_test_ready),
        "status": "passed" if not errors else "blocked",
        "errors": errors,
    }


def validate_y_splits(
    y_train: pd.DataFrame,
    y_valid: pd.DataFrame,
    y_test: pd.DataFrame,
    target_column: str,
) -> dict[str, Any]:
    errors = []

    for split_name, y_part in {
        "train": y_train,
        "valid": y_valid,
        "test": y_test,
    }.items():
        if "SK_ID_CURR" not in y_part.columns:
            errors.append(f"{split_name}: y missing SK_ID_CURR")

        if target_column not in y_part.columns:
            errors.append(f"{split_name}: y missing {target_column}")

        values = sorted(y_part[target_column].dropna().unique().tolist())

        if not set(values).issubset({0, 1}):
            errors.append(f"{split_name}: unexpected target values: {values}")

    return {
        "train_rows": int(len(y_train)),
        "valid_rows": int(len(y_valid)),
        "test_rows": int(len(y_test)),
        "train_positive_rate": float(y_train[target_column].mean()),
        "valid_positive_rate": float(y_valid[target_column].mean()),
        "test_positive_rate": float(y_test[target_column].mean()),
        "status": "passed" if not errors else "blocked",
        "errors": errors,
    }


def save_model_ready_outputs(
    X_train_tree: pd.DataFrame,
    X_valid_tree: pd.DataFrame,
    X_test_tree: pd.DataFrame,
    X_train_linear: pd.DataFrame,
    X_valid_linear: pd.DataFrame,
    X_test_linear: pd.DataFrame,
    y_train: pd.DataFrame,
    y_valid: pd.DataFrame,
    y_test: pd.DataFrame,
) -> dict[str, str]:
    outputs = {
        "X_train_tree": TREE_DIR / "X_train_tree.parquet",
        "X_valid_tree": TREE_DIR / "X_valid_tree.parquet",
        "X_test_tree": TREE_DIR / "X_test_tree.parquet",
        "y_train_tree": TREE_DIR / "y_train.parquet",
        "y_valid_tree": TREE_DIR / "y_valid.parquet",
        "y_test_tree": TREE_DIR / "y_test.parquet",

        "X_train_linear": LINEAR_DIR / "X_train_linear.parquet",
        "X_valid_linear": LINEAR_DIR / "X_valid_linear.parquet",
        "X_test_linear": LINEAR_DIR / "X_test_linear.parquet",
        "y_train_linear": LINEAR_DIR / "y_train.parquet",
        "y_valid_linear": LINEAR_DIR / "y_valid.parquet",
        "y_test_linear": LINEAR_DIR / "y_test.parquet",
    }

    print("[Batch E] Saving model-ready parquet files ...")

    X_train_tree.to_parquet(outputs["X_train_tree"], index=False)
    X_valid_tree.to_parquet(outputs["X_valid_tree"], index=False)
    X_test_tree.to_parquet(outputs["X_test_tree"], index=False)

    y_train.to_parquet(outputs["y_train_tree"], index=False)
    y_valid.to_parquet(outputs["y_valid_tree"], index=False)
    y_test.to_parquet(outputs["y_test_tree"], index=False)

    X_train_linear.to_parquet(outputs["X_train_linear"], index=False)
    X_valid_linear.to_parquet(outputs["X_valid_linear"], index=False)
    X_test_linear.to_parquet(outputs["X_test_linear"], index=False)

    y_train.to_parquet(outputs["y_train_linear"], index=False)
    y_valid.to_parquet(outputs["y_valid_linear"], index=False)
    y_test.to_parquet(outputs["y_test_linear"], index=False)

    return {
        key: relative(value)
        for key, value in outputs.items()
    }


def save_artifacts_and_registries(
    tree_artifact: dict[str, Any],
    linear_artifact: dict[str, Any],
    tree_mapping: dict[str, dict[str, Any]],
    linear_mapping: dict[str, dict[str, Any]],
) -> dict[str, str]:
    print("[Batch E] Saving preprocessing artifacts and registries ...")

    joblib.dump(tree_artifact, TREE_PREPROCESSOR_PATH)
    joblib.dump(linear_artifact, LINEAR_PREPROCESSOR_PATH)

    write_json(
        tree_artifact["preprocessed_feature_columns"],
        PREPROCESSED_FEATURE_COLUMNS_TREE_PATH,
    )

    write_json(
        linear_artifact["preprocessed_feature_columns"],
        PREPROCESSED_FEATURE_COLUMNS_LINEAR_PATH,
    )

    write_json(
        tree_mapping,
        PREPROCESSED_FEATURE_MAPPING_TREE_PATH,
    )

    write_json(
        linear_mapping,
        PREPROCESSED_FEATURE_MAPPING_LINEAR_PATH,
    )

    return {
        "tree_preprocessor": relative(TREE_PREPROCESSOR_PATH),
        "linear_preprocessor": relative(LINEAR_PREPROCESSOR_PATH),
        "preprocessed_feature_columns_tree": relative(PREPROCESSED_FEATURE_COLUMNS_TREE_PATH),
        "preprocessed_feature_columns_linear": relative(PREPROCESSED_FEATURE_COLUMNS_LINEAR_PATH),
        "preprocessed_feature_mapping_tree": relative(PREPROCESSED_FEATURE_MAPPING_TREE_PATH),
        "preprocessed_feature_mapping_linear": relative(PREPROCESSED_FEATURE_MAPPING_LINEAR_PATH),
    }


def write_preprocessing_report(
    input_validation: dict[str, Any],
    y_validation: dict[str, Any],
    feature_groups: dict[str, list[str]],
    tree_validation: dict[str, Any],
    linear_validation: dict[str, Any],
    output_files: dict[str, str],
    artifact_files: dict[str, str],
) -> None:
    md = []

    md.append("# Preprocessing Report\n")
    md.append(f"Created at: `{now_iso()}`\n")

    md.append("## Purpose\n")
    md.append(
        "Batch E fits preprocessing only on the training split and transforms validation/test splits "
        "without refitting. It produces model-ready datasets for tree-based models and linear models.\n"
    )

    md.append("## Input Validation\n")
    md.append(f"- Status: `{input_validation['status']}`")
    md.append(f"- Train rows: `{input_validation['train_rows']}`")
    md.append(f"- Valid rows: `{input_validation['valid_rows']}`")
    md.append(f"- Test rows: `{input_validation['test_rows']}`")
    md.append(f"- Model feature count: `{input_validation['model_feature_count']}`")
    md.append(f"- ID columns: `{input_validation['id_columns']}`")
    md.append(f"- Target column: `{input_validation['target_column']}`")
    md.append(f"- Warning count: `{input_validation['warning_count']}`")
    md.append(f"- Error count: `{input_validation['error_count']}`\n")

    md.append("## Target Validation\n")
    md.append(f"- Status: `{y_validation['status']}`")
    md.append(f"- Train positive rate: `{y_validation['train_positive_rate']:.6f}`")
    md.append(f"- Valid positive rate: `{y_validation['valid_positive_rate']:.6f}`")
    md.append(f"- Test positive rate: `{y_validation['test_positive_rate']:.6f}`\n")

    md.append("## Feature Groups\n")
    md.append(f"- Numeric features: `{len(feature_groups['numeric_features'])}`")
    md.append(f"- Binary features: `{len(feature_groups['binary_features'])}`")
    md.append(f"- Categorical features: `{len(feature_groups['categorical_features'])}`\n")

    md.append("### Categorical Features\n")
    for feature in feature_groups["categorical_features"]:
        md.append(f"- `{feature}`")

    md.append("\n### Binary Features\n")
    for feature in feature_groups["binary_features"]:
        md.append(f"- `{feature}`")

    md.append("\n## Tree Model-Ready Dataset\n")
    md.append(f"- Status: `{tree_validation['status']}`")
    md.append(f"- Train shape: `{tree_validation['train_shape']}`")
    md.append(f"- Valid shape: `{tree_validation['valid_shape']}`")
    md.append(f"- Test shape: `{tree_validation['test_shape']}`")
    md.append(f"- Preprocessed feature count: `{tree_validation['preprocessed_feature_count']}`")
    md.append(f"- Train missing count: `{tree_validation['train_missing_count']}`")
    md.append(f"- Valid missing count: `{tree_validation['valid_missing_count']}`")
    md.append(f"- Test missing count: `{tree_validation['test_missing_count']}`")
    md.append(f"- Train inf count: `{tree_validation['train_inf_count']}`")
    md.append(f"- Valid inf count: `{tree_validation['valid_inf_count']}`")
    md.append(f"- Test inf count: `{tree_validation['test_inf_count']}`\n")

    md.append("## Linear Model-Ready Dataset\n")
    md.append(f"- Status: `{linear_validation['status']}`")
    md.append(f"- Train shape: `{linear_validation['train_shape']}`")
    md.append(f"- Valid shape: `{linear_validation['valid_shape']}`")
    md.append(f"- Test shape: `{linear_validation['test_shape']}`")
    md.append(f"- Preprocessed feature count: `{linear_validation['preprocessed_feature_count']}`")
    md.append(f"- Train missing count: `{linear_validation['train_missing_count']}`")
    md.append(f"- Valid missing count: `{linear_validation['valid_missing_count']}`")
    md.append(f"- Test missing count: `{linear_validation['test_missing_count']}`")
    md.append(f"- Train inf count: `{linear_validation['train_inf_count']}`")
    md.append(f"- Valid inf count: `{linear_validation['valid_inf_count']}`")
    md.append(f"- Test inf count: `{linear_validation['test_inf_count']}`\n")

    md.append("## Preprocessing Strategy\n")
    md.append("- Numeric features for tree models: `SimpleImputer(strategy='median')`")
    md.append("- Numeric features for linear models: `SimpleImputer(strategy='median') + StandardScaler`")
    md.append("- Binary features: `SimpleImputer(strategy='most_frequent')`")
    md.append(f"- Categorical missing token: `{MISSING_CATEGORY_TOKEN}`")
    md.append(f"- Rare category token: `{RARE_CATEGORY_TOKEN}`")
    md.append(f"- Unknown category token: `{UNKNOWN_CATEGORY_TOKEN}`")
    md.append(f"- Rare category threshold: `{RARE_CATEGORY_THRESHOLD}`")
    md.append("- Categorical encoding: `OneHotEncoder(handle_unknown='ignore')`")
    md.append("- Preprocessing fit: `train only`")
    md.append("- Validation/test transform: `using train-fitted artifacts only`\n")

    md.append("## Output Files\n")
    for name, path in output_files.items():
        md.append(f"- `{name}`: `{path}`")

    md.append("\n## Artifact and Registry Files\n")
    for name, path in artifact_files.items():
        md.append(f"- `{name}`: `{path}`")

    errors = []
    errors.extend(input_validation["errors"])
    errors.extend(y_validation["errors"])
    errors.extend(tree_validation["errors"])
    errors.extend(linear_validation["errors"])

    warnings = []
    warnings.extend(input_validation["warnings"])

    if warnings:
        md.append("\n## Warnings\n")
        for warning in warnings:
            md.append(f"- {warning}")

    if errors:
        md.append("\n## Blocking Errors\n")
        for error in errors:
            md.append(f"- {error}")

    PREPROCESSING_REPORT_PATH.write_text("\n".join(md), encoding="utf-8")


def write_manifests_and_summary(
    input_validation: dict[str, Any],
    y_validation: dict[str, Any],
    feature_groups: dict[str, list[str]],
    tree_validation: dict[str, Any],
    linear_validation: dict[str, Any],
    output_files: dict[str, str],
    artifact_files: dict[str, str],
) -> None:
    all_passed = (
        input_validation["status"] == "passed"
        and y_validation["status"] == "passed"
        and tree_validation["status"] == "passed"
        and linear_validation["status"] == "passed"
    )

    preprocessing_manifest = {
        "preprocessing_name": "home_credit_default_risk_preprocessing_v1",
        "created_at": now_iso(),
        "random_state": RANDOM_STATE,
        "source_files": {
            "X_train": relative(X_TRAIN_PATH),
            "y_train": relative(Y_TRAIN_PATH),
            "X_valid": relative(X_VALID_PATH),
            "y_valid": relative(Y_VALID_PATH),
            "X_test": relative(X_TEST_PATH),
            "y_test": relative(Y_TEST_PATH),
            "model_feature_columns": relative(MODEL_FEATURE_COLUMNS_PATH),
            "model_feature_metadata": (
                relative(MODEL_FEATURE_METADATA_PATH)
                if MODEL_FEATURE_METADATA_PATH.exists()
                else None
            ),
            "feature_registry_csv": relative(FEATURE_REGISTRY_CSV_PATH),
        },
        "strategy": {
            "fit_on": "train_only",
            "transform_valid_test": "using_train_fitted_artifacts_only",
            "numeric_tree": "median_imputer",
            "numeric_linear": "median_imputer_plus_standard_scaler",
            "binary": "most_frequent_imputer",
            "categorical": "missing_token_plus_rare_grouping_plus_one_hot",
            "rare_category_threshold": RARE_CATEGORY_THRESHOLD,
        },
        "feature_groups": {
            "numeric_feature_count": len(feature_groups["numeric_features"]),
            "binary_feature_count": len(feature_groups["binary_features"]),
            "categorical_feature_count": len(feature_groups["categorical_features"]),
            "numeric_features": feature_groups["numeric_features"],
            "binary_features": feature_groups["binary_features"],
            "categorical_features": feature_groups["categorical_features"],
        },
        "validation": {
            "input_validation": input_validation,
            "target_validation": y_validation,
            "tree_validation": tree_validation,
            "linear_validation": linear_validation,
        },
        "output_files": output_files,
        "artifact_files": artifact_files,
        "status": "passed" if all_passed else "blocked",
    }

    write_json(preprocessing_manifest, PREPROCESSING_MANIFEST_PATH)

    completed_before = 18
    batch_e_steps = 1
    total = 20
    completed = completed_before + (batch_e_steps if all_passed else 0)
    remaining = total - completed

    batch_summary = {
        "batch_name": "batch_e_preprocessing_layer",
        "created_at": now_iso(),
        "assumption": "Batch A, Batch B, Batch C, and Batch D were already completed.",
        "pipeline_group": "Batch E - Preprocessing Layer",
        "pipeline_group_status": "preprocessing_layer_completed" if all_passed else "blocked",
        "technical_steps_completed": completed,
        "technical_steps_total": total,
        "technical_steps_remaining": remaining,
        "tree_status": tree_validation["status"],
        "linear_status": linear_validation["status"],
        "input_status": input_validation["status"],
        "target_status": y_validation["status"],
        "tree_preprocessed_feature_count": tree_validation["preprocessed_feature_count"],
        "linear_preprocessed_feature_count": linear_validation["preprocessed_feature_count"],
        "feature_groups": {
            "numeric_feature_count": len(feature_groups["numeric_features"]),
            "binary_feature_count": len(feature_groups["binary_features"]),
            "categorical_feature_count": len(feature_groups["categorical_features"]),
        },
        "outputs": {
            **output_files,
            **artifact_files,
            "preprocessing_report": relative(PREPROCESSING_REPORT_PATH),
            "preprocessing_manifest": relative(PREPROCESSING_MANIFEST_PATH),
            "batch_e_summary_report": relative(BATCH_E_SUMMARY_REPORT_PATH),
            "batch_e_summary_manifest": relative(BATCH_E_SUMMARY_MANIFEST_PATH),
        },
        "next_group": "Batch F - Model Training Layer" if all_passed else None,
    }

    write_json(batch_summary, BATCH_E_SUMMARY_MANIFEST_PATH)

    md = []

    md.append("# Batch E Summary — Preprocessing Layer\n")
    md.append("Assumption: Batch A, Batch B, Batch C, and Batch D were already completed.\n")

    md.append("## Batch Status\n")
    md.append(f"- Status: `{'preprocessing_layer_completed' if all_passed else 'blocked'}`")
    md.append(f"- Technical steps completed: `{completed}/{total}`")
    md.append(f"- Technical steps remaining: `{remaining}/{total}`")

    if all_passed:
        md.append("- Next group: `Batch F - Model Training Layer`")
    else:
        md.append("- Next group: blocked until errors are fixed")

    md.append("\n## Feature Groups\n")
    md.append(f"- Numeric features: `{len(feature_groups['numeric_features'])}`")
    md.append(f"- Binary features: `{len(feature_groups['binary_features'])}`")
    md.append(f"- Categorical features: `{len(feature_groups['categorical_features'])}`")

    md.append("\n## Target Splits\n")
    md.append(f"- Train positive rate: `{y_validation['train_positive_rate']:.6f}`")
    md.append(f"- Valid positive rate: `{y_validation['valid_positive_rate']:.6f}`")
    md.append(f"- Test positive rate: `{y_validation['test_positive_rate']:.6f}`")

    md.append("\n## Tree Model-Ready Dataset\n")
    md.append(f"- Status: `{tree_validation['status']}`")
    md.append(f"- Train shape: `{tree_validation['train_shape']}`")
    md.append(f"- Valid shape: `{tree_validation['valid_shape']}`")
    md.append(f"- Test shape: `{tree_validation['test_shape']}`")
    md.append(f"- Feature count: `{tree_validation['preprocessed_feature_count']}`")
    md.append(f"- Missing counts: train=`{tree_validation['train_missing_count']}`, valid=`{tree_validation['valid_missing_count']}`, test=`{tree_validation['test_missing_count']}`")
    md.append(f"- Inf counts: train=`{tree_validation['train_inf_count']}`, valid=`{tree_validation['valid_inf_count']}`, test=`{tree_validation['test_inf_count']}`")

    md.append("\n## Linear Model-Ready Dataset\n")
    md.append(f"- Status: `{linear_validation['status']}`")
    md.append(f"- Train shape: `{linear_validation['train_shape']}`")
    md.append(f"- Valid shape: `{linear_validation['valid_shape']}`")
    md.append(f"- Test shape: `{linear_validation['test_shape']}`")
    md.append(f"- Feature count: `{linear_validation['preprocessed_feature_count']}`")
    md.append(f"- Missing counts: train=`{linear_validation['train_missing_count']}`, valid=`{linear_validation['valid_missing_count']}`, test=`{linear_validation['test_missing_count']}`")
    md.append(f"- Inf counts: train=`{linear_validation['train_inf_count']}`, valid=`{linear_validation['valid_inf_count']}`, test=`{linear_validation['test_inf_count']}`")

    md.append("\n## Output Files\n")
    for name, path in batch_summary["outputs"].items():
        md.append(f"- `{name}`: `{path}`")

    errors = []
    errors.extend(input_validation["errors"])
    errors.extend(y_validation["errors"])
    errors.extend(tree_validation["errors"])
    errors.extend(linear_validation["errors"])

    warnings = []
    warnings.extend(input_validation["warnings"])

    if warnings:
        md.append("\n## Warnings\n")
        for warning in warnings:
            md.append(f"- {warning}")

    if errors:
        md.append("\n## Blocking Errors\n")
        for error in errors:
            md.append(f"- {error}")

    BATCH_E_SUMMARY_REPORT_PATH.write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    print("=== Batch E: Preprocessing Layer ===")
    print("This batch fits preprocessing on train only and transforms valid/test.")
    print("It creates tree-ready and linear-ready model matrices.")
    print("No model training, SHAP, or LLM explanation is performed.\n")

    ensure_inputs_exist()

    model_feature_columns = load_model_feature_columns()
    id_columns = load_id_columns()
    target_column = load_target_column()
    feature_metadata = load_feature_metadata()

    X_train, y_train, X_valid, y_valid, X_test, y_test = load_split_data()

    input_validation = validate_raw_split_inputs(
        X_train=X_train,
        y_train=y_train,
        X_valid=X_valid,
        y_valid=y_valid,
        X_test=X_test,
        y_test=y_test,
        model_feature_columns=model_feature_columns,
        id_columns=id_columns,
        target_column=target_column,
        feature_metadata=feature_metadata,
    )

    y_validation = validate_y_splits(
        y_train=y_train,
        y_valid=y_valid,
        y_test=y_test,
        target_column=target_column,
    )

    if input_validation["status"] != "passed" or y_validation["status"] != "passed":
        write_json(input_validation, MANIFEST_DIR / "batch_e_input_validation_failed.json")
        write_json(y_validation, MANIFEST_DIR / "batch_e_target_validation_failed.json")
        raise RuntimeError("Batch E input/target validation failed.")

    X_train_model = X_train[model_feature_columns].copy()
    X_valid_model = X_valid[model_feature_columns].copy()
    X_test_model = X_test[model_feature_columns].copy()

    feature_groups = infer_feature_groups(
        X_train=X_train_model,
        model_feature_columns=model_feature_columns,
        feature_metadata=feature_metadata,
    )

    print("[Batch E] Feature groups:")
    print(f"- Numeric: {len(feature_groups['numeric_features'])}")
    print(f"- Binary: {len(feature_groups['binary_features'])}")
    print(f"- Categorical: {len(feature_groups['categorical_features'])}")

    X_train_tree, X_valid_tree, X_test_tree, tree_artifact, tree_mapping = build_model_ready_dataset(
        X_train=X_train_model,
        X_valid=X_valid_model,
        X_test=X_test_model,
        numeric_features=feature_groups["numeric_features"],
        categorical_features=feature_groups["categorical_features"],
        binary_features=feature_groups["binary_features"],
        feature_metadata=feature_metadata,
        pipeline_type="tree",
    )

    X_train_linear, X_valid_linear, X_test_linear, linear_artifact, linear_mapping = build_model_ready_dataset(
        X_train=X_train_model,
        X_valid=X_valid_model,
        X_test=X_test_model,
        numeric_features=feature_groups["numeric_features"],
        categorical_features=feature_groups["categorical_features"],
        binary_features=feature_groups["binary_features"],
        feature_metadata=feature_metadata,
        pipeline_type="linear",
    )

    tree_validation = validate_model_ready_dataset(
        X_train_ready=X_train_tree,
        X_valid_ready=X_valid_tree,
        X_test_ready=X_test_tree,
        pipeline_type="tree",
    )

    linear_validation = validate_model_ready_dataset(
        X_train_ready=X_train_linear,
        X_valid_ready=X_valid_linear,
        X_test_ready=X_test_linear,
        pipeline_type="linear",
    )

    if tree_validation["status"] != "passed" or linear_validation["status"] != "passed":
        write_preprocessing_report(
            input_validation=input_validation,
            y_validation=y_validation,
            feature_groups=feature_groups,
            tree_validation=tree_validation,
            linear_validation=linear_validation,
            output_files={},
            artifact_files={},
        )
        raise RuntimeError("Batch E preprocessing validation failed. Check preprocessing_report.md")

    output_files = save_model_ready_outputs(
        X_train_tree=X_train_tree,
        X_valid_tree=X_valid_tree,
        X_test_tree=X_test_tree,
        X_train_linear=X_train_linear,
        X_valid_linear=X_valid_linear,
        X_test_linear=X_test_linear,
        y_train=y_train,
        y_valid=y_valid,
        y_test=y_test,
    )

    artifact_files = save_artifacts_and_registries(
        tree_artifact=tree_artifact,
        linear_artifact=linear_artifact,
        tree_mapping=tree_mapping,
        linear_mapping=linear_mapping,
    )

    write_preprocessing_report(
        input_validation=input_validation,
        y_validation=y_validation,
        feature_groups=feature_groups,
        tree_validation=tree_validation,
        linear_validation=linear_validation,
        output_files=output_files,
        artifact_files=artifact_files,
    )

    write_manifests_and_summary(
        input_validation=input_validation,
        y_validation=y_validation,
        feature_groups=feature_groups,
        tree_validation=tree_validation,
        linear_validation=linear_validation,
        output_files=output_files,
        artifact_files=artifact_files,
    )

    print("\n=== Batch E completed ===")
    print("Produced files:")
    print("- data/processed/model_ready/tree/X_train_tree.parquet")
    print("- data/processed/model_ready/tree/X_valid_tree.parquet")
    print("- data/processed/model_ready/tree/X_test_tree.parquet")
    print("- data/processed/model_ready/tree/y_train.parquet")
    print("- data/processed/model_ready/tree/y_valid.parquet")
    print("- data/processed/model_ready/tree/y_test.parquet")
    print("- data/processed/model_ready/linear/X_train_linear.parquet")
    print("- data/processed/model_ready/linear/X_valid_linear.parquet")
    print("- data/processed/model_ready/linear/X_test_linear.parquet")
    print("- data/processed/model_ready/linear/y_train.parquet")
    print("- data/processed/model_ready/linear/y_valid.parquet")
    print("- data/processed/model_ready/linear/y_test.parquet")
    print("- artifacts/preprocessing/tree_preprocessor.joblib")
    print("- artifacts/preprocessing/linear_preprocessor.joblib")
    print("- ml/registry/preprocessed_feature_columns_tree.json")
    print("- ml/registry/preprocessed_feature_columns_linear.json")
    print("- ml/registry/preprocessed_feature_mapping_tree.json")
    print("- ml/registry/preprocessed_feature_mapping_linear.json")
    print("- data/reports/preprocessing_report.md")
    print("- data/reports/batch_e_preprocessing_summary.md")
    print("- data/manifests/preprocessing_manifest.json")
    print("- data/manifests/batch_e_preprocessing_summary.json")

    print("\nBatch E status: preprocessing_layer_completed")
    print("Next: Batch F - Model Training Layer")


if __name__ == "__main__":
    main()