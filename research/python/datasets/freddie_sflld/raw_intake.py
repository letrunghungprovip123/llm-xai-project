"""Streaming, deterministic raw intake audit for Freddie SFLLD vintage 2024."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterable

from ..receipts import StageReceipt, sha256_path, write_json_atomic
from .schema import (
    LOAN_ID_ORIG_INDEX,
    LOAN_ID_PERF_INDEX,
    ORIGINATION_WIDTH,
    PERFORMANCE_WIDTH,
    PERIOD_INDEX,
)

DATASET_ID = "freddie_sflld_2024"
RAW_INTAKE_STAGE = "freddie_sflld_raw_intake"
RAW_INTAKE_VERSION = "v1"
PATCH_ID = "0005"
QUARTERS = ("2024Q1", "2024Q2", "2024Q3", "2024Q4")
OUTER_MEMBER_PATTERN = re.compile(r"^historical_data_(2024Q[1-4])\.zip$")


def _hash_copy(source: BinaryIO, destination: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
        destination.write(chunk)
    return digest.hexdigest()


def _scan_origination(stream: BinaryIO, *, quarter: str) -> tuple[dict[str, Any], set[bytes]]:
    digest = hashlib.sha256()
    loan_ids: set[bytes] = set()
    rows = malformed = duplicate_ids = prefix_mismatch = 0
    width_histogram: dict[int, int] = {}
    expected_prefix = f"F24Q{quarter[-1]}".encode("ascii")

    for raw_line in stream:
        digest.update(raw_line)
        rows += 1
        width = raw_line.count(b"|") + 1
        width_histogram[width] = width_histogram.get(width, 0) + 1
        if width != ORIGINATION_WIDTH:
            malformed += 1
            continue
        # Loan Identifier is position 20.  Limit the split so the remaining
        # origination payload is never tokenized unnecessarily during M11.
        values = raw_line.rstrip(b"\r\n").split(b"|", LOAN_ID_ORIG_INDEX + 1)
        loan_id = values[LOAN_ID_ORIG_INDEX].strip()
        if not loan_id.startswith(expected_prefix):
            prefix_mismatch += 1
        if loan_id in loan_ids:
            duplicate_ids += 1
        else:
            loan_ids.add(loan_id)

    return (
        {
            "rows": rows,
            "sha256": digest.hexdigest(),
            "expected_width": ORIGINATION_WIDTH,
            "width_histogram": {str(k): v for k, v in sorted(width_histogram.items())},
            "malformed_rows": malformed,
            "unique_loan_ids": len(loan_ids),
            "duplicate_loan_ids": duplicate_ids,
            "loan_id_prefix_mismatch_rows": prefix_mismatch,
        },
        loan_ids,
    )


def _scan_performance(
    stream: BinaryIO,
    *,
    quarter: str,
    origination_ids: set[bytes],
) -> dict[str, Any]:
    digest = hashlib.sha256()
    rows = malformed = orphan_rows = prefix_mismatch = 0
    width_histogram: dict[int, int] = {}
    min_period: str | None = None
    max_period: str | None = None
    expected_prefix = f"F24Q{quarter[-1]}".encode("ascii")
    previous_loan_id: bytes | None = None
    unique_loan_ids = 0
    sort_order_violations = 0

    for raw_line in stream:
        digest.update(raw_line)
        rows += 1
        width = raw_line.count(b"|") + 1
        width_histogram[width] = width_histogram.get(width, 0) + 1
        if width != PERFORMANCE_WIDTH:
            malformed += 1
            continue
        # M11 needs only identifier + reporting period.  Avoid splitting all
        # 35 performance fields for ~20M rows.
        values = raw_line.rstrip(b"\r\n").split(b"|", 2)
        loan_id = values[LOAN_ID_PERF_INDEX].strip()
        if not loan_id.startswith(expected_prefix):
            prefix_mismatch += 1
        if loan_id not in origination_ids:
            orphan_rows += 1
        if previous_loan_id is None or loan_id != previous_loan_id:
            if previous_loan_id is not None and loan_id < previous_loan_id:
                sort_order_violations += 1
            unique_loan_ids += 1
            previous_loan_id = loan_id
        period = values[PERIOD_INDEX].strip().decode("ascii", errors="replace")
        if period:
            min_period = period if min_period is None or period < min_period else min_period
            max_period = period if max_period is None or period > max_period else max_period

    missing_performance = (
        len(origination_ids) - unique_loan_ids if sort_order_violations == 0 else None
    )
    return {
        "rows": rows,
        "sha256": digest.hexdigest(),
        "expected_width": PERFORMANCE_WIDTH,
        "width_histogram": {str(k): v for k, v in sorted(width_histogram.items())},
        "malformed_rows": malformed,
        "unique_loan_ids": unique_loan_ids,
        "orphan_rows": orphan_rows,
        "origination_ids_without_performance": missing_performance,
        "loan_id_prefix_mismatch_rows": prefix_mismatch,
        "loan_id_sort_order_violations": sort_order_violations,
        "min_reporting_period": min_period,
        "max_reporting_period": max_period,
    }


@dataclass(frozen=True)
class RawIntakeResult:
    manifest_path: Path
    audit_path: Path
    receipt_path: Path
    manifest: dict[str, Any]
    audit: dict[str, Any]
    receipt: StageReceipt


class FreddieRawIntakeAuditor:
    def __init__(self, raw_zip: Path) -> None:
        self.raw_zip = raw_zip.expanduser().resolve()
        if not self.raw_zip.is_file():
            raise FileNotFoundError(self.raw_zip)

    def _validate_outer_members(self, archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
        matched: dict[str, zipfile.ZipInfo] = {}
        unexpected: list[str] = []
        for info in archive.infolist():
            match = OUTER_MEMBER_PATTERN.match(info.filename)
            if match:
                matched[match.group(1)] = info
            elif not info.is_dir():
                unexpected.append(info.filename)
        if unexpected:
            raise ValueError(f"unexpected non-directory outer ZIP members: {unexpected}")
        if set(matched) != set(QUARTERS):
            raise ValueError(
                f"expected quarters {list(QUARTERS)}, found {sorted(matched)}"
            )
        return matched

    def run(self, output_dir: Path) -> RawIntakeResult:
        output_dir = output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        raw_sha = sha256_path(self.raw_zip)
        quarter_payloads: list[dict[str, Any]] = []

        with zipfile.ZipFile(self.raw_zip) as outer, tempfile.TemporaryDirectory(
            prefix="freddie_sflld_intake_"
        ) as temporary_directory:
            members = self._validate_outer_members(outer)
            temp_root = Path(temporary_directory)
            for quarter in QUARTERS:
                info = members[quarter]
                nested_path = temp_root / f"{quarter}.zip"
                with outer.open(info) as source, nested_path.open("wb") as destination:
                    nested_sha = _hash_copy(source, destination)
                if not zipfile.is_zipfile(nested_path):
                    raise ValueError(f"nested member is not a valid ZIP: {info.filename}")

                with zipfile.ZipFile(nested_path) as nested:
                    expected_orig = f"orig_{quarter}.txt"
                    expected_perf = f"perf_{quarter}.txt"
                    names = sorted(item.filename for item in nested.infolist() if not item.is_dir())
                    if names != sorted([expected_orig, expected_perf]):
                        raise ValueError(
                            f"{quarter}: expected {[expected_orig, expected_perf]}, found {names}"
                        )
                    with nested.open(expected_orig) as orig_stream:
                        orig_stats, orig_ids = _scan_origination(orig_stream, quarter=quarter)
                    with nested.open(expected_perf) as perf_stream:
                        perf_stats = _scan_performance(
                            perf_stream,
                            quarter=quarter,
                            origination_ids=orig_ids,
                        )
                    quarter_payloads.append(
                        {
                            "quarter": quarter,
                            "outer_member": info.filename,
                            "outer_member_compressed_bytes": info.compress_size,
                            "outer_member_uncompressed_bytes": info.file_size,
                            "nested_zip_sha256": nested_sha,
                            "origination": {"member": expected_orig, **orig_stats},
                            "performance": {"member": expected_perf, **perf_stats},
                        }
                    )

        total_orig = sum(q["origination"]["rows"] for q in quarter_payloads)
        total_perf = sum(q["performance"]["rows"] for q in quarter_payloads)
        malformed = sum(
            q["origination"]["malformed_rows"] + q["performance"]["malformed_rows"]
            for q in quarter_payloads
        )
        duplicate_orig = sum(q["origination"]["duplicate_loan_ids"] for q in quarter_payloads)
        orphan_rows = sum(q["performance"]["orphan_rows"] for q in quarter_payloads)
        if any(q["performance"]["origination_ids_without_performance"] is None for q in quarter_payloads):
            raise ValueError("performance loan identifiers are not grouped/sorted; cannot certify coverage")
        missing_perf = sum(
            q["performance"]["origination_ids_without_performance"] for q in quarter_payloads
        )
        prefix_mismatch = sum(
            q["origination"]["loan_id_prefix_mismatch_rows"]
            + q["performance"]["loan_id_prefix_mismatch_rows"]
            for q in quarter_payloads
        )
        min_period = min(
            q["performance"]["min_reporting_period"]
            for q in quarter_payloads
            if q["performance"]["min_reporting_period"] is not None
        )
        max_period = max(
            q["performance"]["max_reporting_period"]
            for q in quarter_payloads
            if q["performance"]["max_reporting_period"] is not None
        )

        manifest = {
            "schema_version": "freddie_sflld_raw_manifest_v1",
            "dataset_id": DATASET_ID,
            "source": {
                "filename": self.raw_zip.name,
                "sha256": raw_sha,
                "outer_zip_members": [q["outer_member"] for q in quarter_payloads],
            },
            "layout": {
                "origination_width": ORIGINATION_WIDTH,
                "performance_width": PERFORMANCE_WIDTH,
                "quarter_count": len(quarter_payloads),
            },
            "quarters": quarter_payloads,
        }
        audit = {
            "schema_version": "freddie_sflld_intake_audit_v1",
            "dataset_id": DATASET_ID,
            "source_sha256": raw_sha,
            "totals": {
                "origination_rows": total_orig,
                "performance_rows": total_perf,
                "malformed_rows": malformed,
                "duplicate_origination_loan_ids": duplicate_orig,
                "performance_orphan_rows": orphan_rows,
                "origination_ids_without_performance": missing_perf,
                "loan_id_prefix_mismatch_rows": prefix_mismatch,
                "min_reporting_period": min_period,
                "max_reporting_period": max_period,
            },
            "invariants": {
                "four_quarters_present": "PASS" if len(quarter_payloads) == 4 else "FAIL",
                "expected_schema_widths": "PASS" if malformed == 0 else "FAIL",
                "origination_loan_ids_unique": "PASS" if duplicate_orig == 0 else "FAIL",
                "performance_ids_resolve_to_origination": "PASS" if orphan_rows == 0 else "FAIL",
                "all_origination_ids_have_performance": "PASS" if missing_perf == 0 else "FAIL",
                "quarter_identity_consistent": "PASS" if prefix_mismatch == 0 else "FAIL",
                "performance_loan_ids_sorted": "PASS" if all(q["performance"]["loan_id_sort_order_violations"] == 0 for q in quarter_payloads) else "FAIL",
            },
        }
        if any(value != "PASS" for value in audit["invariants"].values()):
            raise ValueError(f"Freddie raw intake invariant failure: {audit['invariants']}")

        manifest_path = output_dir / "freddie_sflld_2024_raw_manifest_v1.json"
        audit_path = output_dir / "freddie_sflld_2024_intake_audit_v1.json"
        write_json_atomic(manifest_path, manifest)
        write_json_atomic(audit_path, audit)
        receipt = StageReceipt(
            stage=RAW_INTAKE_STAGE,
            stage_version=RAW_INTAKE_VERSION,
            dataset_id=DATASET_ID,
            patch_id=PATCH_ID,
            input_fingerprints={"raw_source": raw_sha},
            config_fingerprints={},
            output_fingerprints={
                manifest_path.name: sha256_path(manifest_path),
                audit_path.name: sha256_path(audit_path),
            },
            invariants=audit["invariants"],
            status="PASS",
        )
        receipt_path = output_dir / "freddie_sflld_2024_m11_receipt_v1.json"
        write_json_atomic(receipt_path, receipt.to_dict())
        return RawIntakeResult(
            manifest_path=manifest_path,
            audit_path=audit_path,
            receipt_path=receipt_path,
            manifest=manifest,
            audit=audit,
            receipt=receipt,
        )
