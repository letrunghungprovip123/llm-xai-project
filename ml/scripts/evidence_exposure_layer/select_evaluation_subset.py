import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


LEVELS = {"S0", "S1", "S2", "S3", "S4", "S5"}

TARGET_STRATA = [
    "top_high_risk",
    "low_risk",
    "true_positive",
    "false_positive",
    "false_negative",
    "near_threshold",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a deterministic 36-case Batch I evaluation subset."
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Full 120-case evidence_packages.jsonl",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for the 36-case subset artifacts",
    )

    parser.add_argument(
        "--cases-per-stratum",
        type=int,
        default=6,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=20260711,
    )

    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON at line {line_number}: {error}"
                ) from error

            if not isinstance(value, dict):
                raise ValueError(
                    f"Line {line_number} must contain a JSON object."
                )

            records.append(value)

    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False))
            file.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def normalize_stratum(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip().lower()

    aliases = {
        "tp": "true_positive",
        "true positive": "true_positive",
        "true_positive": "true_positive",
        "fp": "false_positive",
        "false positive": "false_positive",
        "false_positive": "false_positive",
        "fn": "false_negative",
        "false negative": "false_negative",
        "false_negative": "false_negative",
        "top high risk": "top_high_risk",
        "top_high_risk": "top_high_risk",
        "high_risk": "top_high_risk",
        "low risk": "low_risk",
        "low_risk": "low_risk",
        "near threshold": "near_threshold",
        "near_threshold": "near_threshold",
    }

    return aliases.get(text, text)


def read_internal_metadata(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("internal_metadata")

    if isinstance(value, dict):
        return value

    return {}


def read_customer_metadata(record: dict[str, Any]) -> dict[str, Any]:
    internal = read_internal_metadata(record)
    customer = internal.get("customer")

    if isinstance(customer, dict):
        return customer

    return {}


def get_stratum(record: dict[str, Any]) -> str | None:
    customer = read_customer_metadata(record)
    internal = read_internal_metadata(record)

    candidates = [
        customer.get("case_type"),
        customer.get("selection_stratum"),
        internal.get("case_type"),
        internal.get("selection_stratum"),
    ]

    for candidate in candidates:
        normalized = normalize_stratum(candidate)

        if normalized:
            return normalized

    return None


def get_case_id(record: dict[str, Any]) -> str:
    value = record.get("source_ir_id")

    if value is None:
        raise ValueError("Record is missing source_ir_id.")

    return str(value)


def get_level(record: dict[str, Any]) -> str:
    value = str(record.get("evidence_level", ""))

    if value not in LEVELS:
        raise ValueError(
            f"Case {get_case_id(record)} has invalid evidence level: {value}"
        )

    return value


def read_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_selection_context(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("prompt_payload")

    if not isinstance(payload, dict):
        return {}

    context = payload.get("selection_context")

    if isinstance(context, dict):
        return context

    return {}


def calculate_difficulty(record: dict[str, Any]) -> float:
    """
    Compute difficulty only from pre-generation input metadata.

    Higher score means the case is harder for narrative generation.
    S4 is preferred because it carries entropy, coverage and evidence density.
    """
    context = get_selection_context(record)
    score = 0.0

    entropy = read_number(
        context.get("shap_entropy")
        or context.get("normalized_entropy")
    )

    if entropy is not None:
        score += entropy * 4.0

    entropy_level = str(
        context.get("entropy_level", "")
    ).strip().lower()

    if entropy_level == "high":
        score += 2.0
    elif entropy_level == "medium":
        score += 1.0

    coverage_status = str(
        context.get("coverage_status", "")
    ).strip().upper()

    if coverage_status == "BELOW_TARGET":
        score += 2.0

    selected_count = read_number(
        context.get("selected_evidence_count")
    )

    if selected_count is not None:
        score += min(selected_count, 20.0) / 10.0

    concept_count = read_number(
        context.get("concept_count")
        or context.get("selected_concept_count")
    )

    if concept_count is not None:
        score += min(concept_count, 10.0) / 10.0

    mixed_count = read_number(
        context.get("mixed_concept_group_count")
    )

    if mixed_count is not None:
        score += min(mixed_count, 5.0) / 5.0

    payload = record.get("prompt_payload")

    if isinstance(payload, dict):
        prediction = payload.get("prediction")

        if isinstance(prediction, dict):
            probability = read_number(prediction.get("probability"))
            threshold = read_number(prediction.get("threshold"))

            if probability is not None and threshold is not None:
                distance = abs(probability - threshold)

                # Near-threshold cases are harder.
                score += max(0.0, 1.0 - min(distance / 0.25, 1.0))

    return score


def deterministic_tiebreak(case_id: str, seed: int) -> str:
    return hashlib.sha256(
        f"{seed}|{case_id}".encode("utf-8")
    ).hexdigest()


def validate_case_matrix(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    cases: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    for record in records:
        case_id = get_case_id(record)
        level = get_level(record)

        if level in cases[case_id]:
            raise ValueError(
                f"Duplicate package for case={case_id}, level={level}."
            )

        cases[case_id][level] = record

    invalid_cases: list[str] = []

    for case_id, level_map in cases.items():
        missing_levels = LEVELS - set(level_map)

        if missing_levels:
            invalid_cases.append(
                f"{case_id}: missing {sorted(missing_levels)}"
            )

    if invalid_cases:
        details = "\n".join(invalid_cases[:20])
        raise ValueError(
            f"Some cases do not contain all S0-S5 packages:\n{details}"
        )

    return dict(cases)


def build_case_rows(
    cases: dict[str, dict[str, dict[str, Any]]],
    seed: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for case_id, level_map in cases.items():
        representative = level_map["S4"]
        stratum = get_stratum(representative)

        if stratum is None:
            raise ValueError(
                f"Could not determine stratum for case: {case_id}"
            )

        difficulty = calculate_difficulty(representative)

        rows.append(
            {
                "case_id": case_id,
                "stratum": stratum,
                "difficulty_score": difficulty,
                "tie_break": deterministic_tiebreak(case_id, seed),
            }
        )

    return rows


def select_balanced_cases(
    case_rows: list[dict[str, Any]],
    cases_per_stratum: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in case_rows:
        grouped[row["stratum"]].append(row)

    selected: list[dict[str, Any]] = []

    for stratum in TARGET_STRATA:
        rows = grouped.get(stratum, [])

        if len(rows) < cases_per_stratum:
            raise ValueError(
                f"Stratum {stratum} has only {len(rows)} cases; "
                f"{cases_per_stratum} are required."
            )

        rows.sort(
            key=lambda item: (
                item["difficulty_score"],
                item["tie_break"],
            )
        )

        if cases_per_stratum != 6:
            raise ValueError(
                "This selector currently expects exactly 6 cases per stratum."
            )

        easy = rows[:2]

        middle_start = max(0, len(rows) // 2 - 1)
        medium = rows[middle_start:middle_start + 2]

        hard = rows[-2:]

        stratum_selected: list[dict[str, Any]] = []

        for difficulty_group, items in [
            ("easy", easy),
            ("medium", medium),
            ("hard", hard),
        ]:
            for item in items:
                copied = dict(item)
                copied["difficulty_group"] = difficulty_group
                stratum_selected.append(copied)

        selected_ids = {
            item["case_id"] for item in stratum_selected
        }

        if len(selected_ids) != 6:
            raise ValueError(
                f"Selection overlap occurred in stratum {stratum}. "
                "The stratum does not contain enough distinct cases."
            )

        selected.extend(stratum_selected)

    return selected


def write_selected_case_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "case_id",
                "stratum",
                "difficulty_group",
                "difficulty_score",
            ],
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    "case_id": row["case_id"],
                    "stratum": row["stratum"],
                    "difficulty_group": row["difficulty_group"],
                    "difficulty_score": round(
                        float(row["difficulty_score"]),
                        8,
                    ),
                }
            )


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    records = read_jsonl(input_path)
    cases = validate_case_matrix(records)

    case_rows = build_case_rows(cases, args.seed)

    selected_rows = select_balanced_cases(
        case_rows,
        args.cases_per_stratum,
    )

    selected_ids = {
        row["case_id"] for row in selected_rows
    }

    selected_records = [
        record
        for record in records
        if get_case_id(record) in selected_ids
    ]

    selected_records.sort(
        key=lambda record: (
            TARGET_STRATA.index(
                get_stratum(record) or ""
            ),
            get_case_id(record),
            get_level(record),
        )
    )

    expected_case_count = (
        len(TARGET_STRATA) * args.cases_per_stratum
    )

    expected_record_count = expected_case_count * len(LEVELS)

    if len(selected_ids) != expected_case_count:
        raise ValueError(
            f"Expected {expected_case_count} cases, "
            f"found {len(selected_ids)}."
        )

    if len(selected_records) != expected_record_count:
        raise ValueError(
            f"Expected {expected_record_count} packages, "
            f"found {len(selected_records)}."
        )

    subset_path = output_dir / "evidence_packages_36.jsonl"
    csv_path = output_dir / "selected_case_ids_36.csv"
    manifest_path = output_dir / "selection_manifest.json"

    write_jsonl(subset_path, selected_records)
    write_selected_case_csv(csv_path, selected_rows)

    manifest = {
        "subset_id": "aws_budget_subset_36_v1",
        "source_input_path": str(input_path),
        "source_input_sha256": sha256_file(input_path),
        "selection_method": (
            "deterministic stratified difficulty-balanced selection"
        ),
        "seed": args.seed,
        "target_strata": TARGET_STRATA,
        "cases_per_stratum": args.cases_per_stratum,
        "difficulty_groups_per_stratum": {
            "easy": 2,
            "medium": 2,
            "hard": 2,
        },
        "selected_case_count": len(selected_ids),
        "evidence_levels": sorted(LEVELS),
        "selected_package_count": len(selected_records),
        "subset_path": str(subset_path),
        "subset_sha256": sha256_file(subset_path),
        "selected_case_ids_csv": str(csv_path),
        "selection_performed_before_aws_generation": True,
    }

    with manifest_path.open("w", encoding="utf-8") as file:
        json.dump(
            manifest,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("Subset creation complete")
    print("selected_case_count:", len(selected_ids))
    print("selected_package_count:", len(selected_records))
    print("subset:", subset_path)
    print("selected cases:", csv_path)
    print("manifest:", manifest_path)


if __name__ == "__main__":
    main()