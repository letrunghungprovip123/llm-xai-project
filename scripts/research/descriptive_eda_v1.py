from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path.cwd()

OUT_ROOT = ROOT / "data" / "reports" / "descriptive_eda_v1"

DATASETS = {
    "HOME_CREDIT": ROOT / (
        ".researchops/workspaces/home_credit_default_risk/"
        "home_credit_common_ml_v1/hc-common-ml-preprocess-001/"
        "data/processed/splits"
    ),
    "FREDDIE": ROOT / (
        ".researchops/workspaces/freddie_sflld_2024/"
        "freddie_sflld_2024_replication_v1/freddie-common-ml-001/"
        "data/processed/splits"
    ),
}

ID_COLUMNS = {"case_id", "source_entity_id"}
TARGET = "target"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_float(x):
    if x is None or pd.isna(x) or np.isinf(x):
        return None
    return float(x)


def skew_direction(x):
    if x is None or pd.isna(x):
        return "unknown"
    if x > 0.5:
        return "right_skewed"
    if x < -0.5:
        return "left_skewed"
    return "approximately_symmetric"


def check_alignment(X: pd.DataFrame, y: pd.DataFrame, dataset: str, split: str):
    if len(X) != len(y):
        raise ValueError(f"{dataset}/{split}: X/y row-count mismatch")

    for col in ["case_id", "source_entity_id"]:
        if col not in X.columns or col not in y.columns:
            raise ValueError(f"{dataset}/{split}: missing alignment key {col}")

        left = X[col].astype(str).reset_index(drop=True)
        right = y[col].astype(str).reset_index(drop=True)

        if not left.equals(right):
            raise ValueError(f"{dataset}/{split}: row alignment mismatch on {col}")

    if TARGET not in y.columns:
        raise ValueError(f"{dataset}/{split}: target column missing")


def numeric_statistics(X: pd.DataFrame, y: pd.DataFrame) -> pd.DataFrame:
    predictors = X.drop(columns=[c for c in ID_COLUMNS if c in X.columns])
    numeric_cols = predictors.select_dtypes(include=[np.number]).columns

    target = y[TARGET].reset_index(drop=True)

    rows = []

    for col in numeric_cols:
        s = pd.to_numeric(predictors[col], errors="coerce").reset_index(drop=True)
        non_null = s.dropna()

        if len(non_null) == 0:
            continue

        q01 = non_null.quantile(0.01)
        q05 = non_null.quantile(0.05)
        q25 = non_null.quantile(0.25)
        q50 = non_null.quantile(0.50)
        q75 = non_null.quantile(0.75)
        q95 = non_null.quantile(0.95)
        q99 = non_null.quantile(0.99)

        iqr = q75 - q25
        lower = q25 - 1.5 * iqr
        upper = q75 + 1.5 * iqr

        outlier_mask = s.notna() & ((s < lower) | (s > upper))
        outlier_count = int(outlier_mask.sum())

        mean = non_null.mean()
        std = non_null.std()
        var = non_null.var()
        skew = non_null.skew()
        kurt = non_null.kurt()

        t0 = s[target == 0].dropna()
        t1 = s[target == 1].dropna()

        corr = None
        try:
            if s.nunique(dropna=True) > 1:
                corr = s.corr(target)
        except Exception:
            corr = None

        rows.append({
            "feature": col,
            "row_count": len(s),
            "non_null_count": int(s.notna().sum()),
            "missing_count": int(s.isna().sum()),
            "missing_rate": float(s.isna().mean()),
            "unique_count": int(s.nunique(dropna=True)),

            "mean": safe_float(mean),
            "std": safe_float(std),
            "variance": safe_float(var),
            "min": safe_float(non_null.min()),

            "p01": safe_float(q01),
            "p05": safe_float(q05),
            "p25": safe_float(q25),
            "median": safe_float(q50),
            "p75": safe_float(q75),
            "p95": safe_float(q95),
            "p99": safe_float(q99),

            "max": safe_float(non_null.max()),
            "iqr": safe_float(iqr),

            "skewness": safe_float(skew),
            "skew_direction": skew_direction(skew),
            "kurtosis_excess": safe_float(kurt),

            "zero_count": int((s == 0).sum()),
            "zero_rate_all_rows": float((s == 0).sum() / len(s)),

            "iqr_outlier_count": outlier_count,
            "iqr_outlier_rate_all_rows": float(outlier_count / len(s)),
            "iqr_outlier_rate_nonmissing":
                float(outlier_count / len(non_null)) if len(non_null) else None,

            "target_correlation": safe_float(corr),

            "target_0_non_null": int(len(t0)),
            "target_1_non_null": int(len(t1)),

            "mean_target_0": safe_float(t0.mean()) if len(t0) else None,
            "mean_target_1": safe_float(t1.mean()) if len(t1) else None,
            "mean_diff_target_1_minus_0":
                safe_float(t1.mean() - t0.mean()) if len(t0) and len(t1) else None,

            "median_target_0": safe_float(t0.median()) if len(t0) else None,
            "median_target_1": safe_float(t1.median()) if len(t1) else None,
            "median_diff_target_1_minus_0":
                safe_float(t1.median() - t0.median())
                if len(t0) and len(t1) else None,
        })

    return pd.DataFrame(rows)


def categorical_statistics(X: pd.DataFrame, y: pd.DataFrame):
    predictors = X.drop(columns=[c for c in ID_COLUMNS if c in X.columns])

    categorical_cols = predictors.select_dtypes(
        exclude=[np.number]
    ).columns

    target = y[TARGET].reset_index(drop=True)

    summary_rows = []
    frequency_rows = []

    for col in categorical_cols:
        s = predictors[col].astype("string").reset_index(drop=True)
        s_filled = s.fillna("<MISSING>")

        counts = s_filled.value_counts(dropna=False)
        mode_value = counts.index[0] if len(counts) else None
        mode_count = int(counts.iloc[0]) if len(counts) else 0

        summary_rows.append({
            "feature": col,
            "row_count": len(s),
            "non_null_count": int(s.notna().sum()),
            "missing_count": int(s.isna().sum()),
            "missing_rate": float(s.isna().mean()),
            "unique_count_nonmissing": int(s.nunique(dropna=True)),
            "mode": None if mode_value is None else str(mode_value),
            "mode_count": mode_count,
            "mode_rate": float(mode_count / len(s)) if len(s) else None,
        })

        levels = sorted(s_filled.unique().tolist())

        n0 = int((target == 0).sum())
        n1 = int((target == 1).sum())

        for level in levels:
            mask = s_filled == level

            count_all = int(mask.sum())
            count_t0 = int((mask & (target == 0)).sum())
            count_t1 = int((mask & (target == 1)).sum())

            frequency_rows.append({
                "feature": col,
                "category": str(level),

                "count_all": count_all,
                "rate_all": float(count_all / len(s)),

                "count_target_0": count_t0,
                "rate_within_target_0":
                    float(count_t0 / n0) if n0 else None,

                "count_target_1": count_t1,
                "rate_within_target_1":
                    float(count_t1 / n1) if n1 else None,
            })

    return (
        pd.DataFrame(summary_rows),
        pd.DataFrame(frequency_rows),
    )


def split_profile(dataset_root: Path, dataset_name: str) -> pd.DataFrame:
    rows = []

    for split in ["train", "valid", "test"]:
        xp = dataset_root / f"X_{split}.parquet"
        yp = dataset_root / f"y_{split}.parquet"

        X = pd.read_parquet(xp)
        y = pd.read_parquet(yp)

        check_alignment(X, y, dataset_name, split)

        predictors = [
            c for c in X.columns
            if c not in ID_COLUMNS
        ]

        rows.append({
            "dataset": dataset_name,
            "split": split,
            "rows": len(X),
            "predictor_count": len(predictors),
            "positive_count": int((y[TARGET] == 1).sum()),
            "negative_count": int((y[TARGET] == 0).sum()),
            "positive_rate": float(y[TARGET].mean()),
            "duplicate_case_id": int(X["case_id"].duplicated().sum()),
            "duplicate_source_entity_id":
                int(X["source_entity_id"].duplicated().sum()),
        })

    return pd.DataFrame(rows)


def write_summary(
    dataset_name: str,
    out_dir: Path,
    numeric: pd.DataFrame,
    categorical: pd.DataFrame,
    split_df: pd.DataFrame,
):
    train = split_df[split_df["split"] == "train"].iloc[0]

    top_missing_num = (
        numeric.sort_values("missing_rate", ascending=False)
        .head(10)[["feature", "missing_rate"]]
    )

    top_skew = numeric.assign(
        abs_skew=numeric["skewness"].abs()
    ).sort_values(
        "abs_skew", ascending=False
    ).head(10)[
        ["feature", "skewness", "skew_direction"]
    ]

    lines = [
        f"# {dataset_name} — Descriptive EDA v1",
        "",
        "## Scope",
        "",
        "- Descriptive characterization only.",
        "- Uses frozen canonical train/validation/test splits.",
        "- Does not refit preprocessing or predictive models.",
        "- Does not alter targets, XAI, LLM generations, or certified results.",
        "",
        "## Training population",
        "",
        f"- Rows: {int(train['rows']):,}",
        f"- Predictors: {int(train['predictor_count'])}",
        f"- Positive cases: {int(train['positive_count']):,}",
        f"- Negative cases: {int(train['negative_count']):,}",
        f"- Positive prevalence: {train['positive_rate']:.8f}",
        f"- Numeric/binary dtype predictors: {len(numeric)}",
        f"- Categorical predictors: {len(categorical)}",
        "",
        "## Top missing numeric features",
        "",
    ]

    for _, r in top_missing_num.iterrows():
        lines.append(
            f"- {r['feature']}: {r['missing_rate']:.4%}"
        )

    lines += [
        "",
        "## Most skewed numeric features",
        "",
    ]

    for _, r in top_skew.iterrows():
        lines.append(
            f"- {r['feature']}: skew={r['skewness']:.6f} "
            f"({r['skew_direction']})"
        )

    (out_dir / "EDA_SUMMARY.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main():
    if OUT_ROOT.exists():
        raise FileExistsError(
            f"Output folder already exists: {OUT_ROOT}\n"
            "Refusing to overwrite existing EDA artifacts."
        )

    OUT_ROOT.mkdir(parents=True)

    global_manifest = {
        "analysis_id": "descriptive_eda_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "bounded_descriptive_analysis",
        "scientific_role": (
            "supplementary dataset characterization; "
            "does not modify frozen ML/XAI/LLM results"
        ),
        "datasets": {},
    }

    for dataset_name, dataset_root in DATASETS.items():
        print("\n" + "=" * 80)
        print(dataset_name)
        print("=" * 80)

        out_dir = OUT_ROOT / dataset_name
        out_dir.mkdir()

        input_files = {}

        for split in ["train", "valid", "test"]:
            for kind in ["X", "y"]:
                p = dataset_root / f"{kind}_{split}.parquet"

                if not p.exists():
                    raise FileNotFoundError(p)

                input_files[str(p.relative_to(ROOT))] = {
                    "bytes": p.stat().st_size,
                    "sha256": sha256_file(p),
                }

        X_train = pd.read_parquet(dataset_root / "X_train.parquet")
        y_train = pd.read_parquet(dataset_root / "y_train.parquet")

        check_alignment(X_train, y_train, dataset_name, "train")

        predictor_cols = [
            c for c in X_train.columns
            if c not in ID_COLUMNS
        ]

        print("Rows:", len(X_train))
        print("Predictors:", len(predictor_cols))

        num = numeric_statistics(X_train, y_train)
        cat_summary, cat_freq = categorical_statistics(
            X_train,
            y_train,
        )

        splits = split_profile(dataset_root, dataset_name)

        num.to_csv(
            out_dir / "numeric_train_statistics.csv",
            index=False,
        )

        cat_summary.to_csv(
            out_dir / "categorical_train_summary.csv",
            index=False,
        )

        cat_freq.to_csv(
            out_dir / "categorical_train_frequency.csv",
            index=False,
        )

        splits.to_csv(
            out_dir / "split_profile.csv",
            index=False,
        )

        top_missing = pd.concat([
            num[["feature", "missing_rate"]].assign(type="numeric"),
            cat_summary[["feature", "missing_rate"]].assign(
                type="categorical"
            ),
        ]).sort_values(
            "missing_rate",
            ascending=False,
        )

        top_missing.to_csv(
            out_dir / "top_missing_features.csv",
            index=False,
        )

        num.assign(
            abs_skewness=num["skewness"].abs()
        ).sort_values(
            "abs_skewness",
            ascending=False,
        ).to_csv(
            out_dir / "top_skewed_features.csv",
            index=False,
        )

        num.assign(
            abs_target_correlation=num["target_correlation"].abs()
        ).sort_values(
            "abs_target_correlation",
            ascending=False,
            na_position="last",
        ).to_csv(
            out_dir / "top_target_associations.csv",
            index=False,
        )

        manifest = {
            "dataset": dataset_name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "input_root": str(dataset_root.relative_to(ROOT)),
            "input_files": input_files,
            "training_rows": len(X_train),
            "predictor_count": len(predictor_cols),
            "numeric_predictor_count": len(num),
            "categorical_predictor_count": len(cat_summary),
            "target_column": TARGET,
            "excluded_identifier_columns": sorted(ID_COLUMNS),
            "skew_direction_rule": {
                "right_skewed": "> 0.5",
                "left_skewed": "< -0.5",
                "approximately_symmetric": "[-0.5, 0.5]",
            },
            "kurtosis_definition": "pandas excess kurtosis",
            "target_correlation_role": (
                "descriptive Pearson correlation with binary target; "
                "not causal inference"
            ),
        }

        (out_dir / "manifest.json").write_text(
            json.dumps(
                manifest,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        write_summary(
            dataset_name,
            out_dir,
            num,
            cat_summary,
            splits,
        )

        global_manifest["datasets"][dataset_name] = manifest

        print("Numeric:", len(num))
        print("Categorical:", len(cat_summary))
        print("DONE:", out_dir)

    (OUT_ROOT / "manifest.json").write_text(
        json.dumps(
            global_manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\nDESCRIPTIVE_EDA_V1 = PASS")
    print("Output:", OUT_ROOT)


if __name__ == "__main__":
    main()
