"""Deterministic 12-month serious-delinquency target for Freddie SFLLD 2024.

The study horizon is anchored to the *origination First Payment Date*, not the
monthly ``Loan Age`` field. Freddie resets Loan Age after a modification; using
it directly can move seasoned loans back into months 1..12.
"""
from __future__ import annotations

import csv
import json
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..receipts import StageReceipt, load_receipt, sha256_path, write_json_atomic
from .raw_intake import DATASET_ID, QUARTERS, _hash_copy

TARGET_STAGE = "freddie_sflld_target_12m"
TARGET_STAGE_VERSION = "v1"
PATCH_ID = "0006"
CHUNK_ROWS = 500_000
TARGET_COLUMNS = (
    "source_entity_id",
    "target",
    "target_observation_status",
    "target_event",
    "first_payment_period",
    "first_observed_payment_index",
    "last_observed_payment_index",
    "event_payment_index",
    "terminal_zero_balance_code",
    "terminal_payment_index",
    "observed_horizon_months",
    "first_reporting_period",
    "last_reporting_period",
    "censor_reason",
)


@dataclass(frozen=True)
class TargetProtocol:
    target_id: str
    horizon_min: int
    horizon_max: int
    serious_min_cycles: int
    reo_status: str
    unknown_status: str
    serious_zero_balance_codes: frozenset[str]
    clean_negative_zero_balance_codes: frozenset[str]
    censoring_zero_balance_codes: frozenset[str]

    @classmethod
    def load(cls, path: Path) -> "TargetProtocol":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "freddie_target_protocol_v1":
            raise ValueError("unsupported Freddie target protocol schema_version")
        if payload.get("dataset_id") != DATASET_ID:
            raise ValueError("target protocol dataset_id mismatch")
        if payload.get("horizon_anchor") != "origination_first_payment_date":
            raise ValueError("v1 target horizon must be anchored to origination First Payment Date")
        if payload.get("raw_loan_age_used_for_horizon") is not False:
            raise ValueError("raw Loan Age must not define the v1 target horizon")
        horizon_min = int(payload["horizon_payment_index_min"])
        horizon_max = int(payload["horizon_payment_index_max"])
        if (horizon_min, horizon_max) != (1, 12):
            raise ValueError("v1 study protocol requires scheduled payment months 1..12")
        return cls(
            target_id=str(payload["target_id"]),
            horizon_min=horizon_min,
            horizon_max=horizon_max,
            serious_min_cycles=int(payload["serious_delinquency_min_cycles"]),
            reo_status=str(payload["reo_status"]),
            unknown_status=str(payload["unknown_delinquency_status"]),
            serious_zero_balance_codes=frozenset(map(str, payload["serious_zero_balance_codes"])),
            clean_negative_zero_balance_codes=frozenset(map(str, payload["clean_negative_zero_balance_codes"])),
            censoring_zero_balance_codes=frozenset(map(str, payload["censoring_zero_balance_codes"])),
        )


def _period_to_ordinal(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").astype("Int64")
    year = numeric // 100
    month = numeric % 100
    invalid = numeric.isna() | month.lt(1) | month.gt(12)
    if bool(invalid.any()):
        bad = series.loc[invalid].head(10).tolist()
        raise ValueError(f"invalid YYYYMM values: {bad}")
    return (year * 12 + month).astype("int64")


def payment_index(reporting_period: str, first_payment_period: str) -> int:
    frame = pd.Series([reporting_period, first_payment_period], dtype="string")
    ordinals = _period_to_ordinal(frame)
    return int(ordinals.iloc[0] - ordinals.iloc[1] + 1)


def _load_anchors_frame(stream) -> pd.DataFrame:
    orig = pd.read_csv(
        stream,
        sep="|",
        header=None,
        usecols=[1, 19],
        names=["first_payment_period", "source_entity_id"],
        dtype="string",
        na_filter=False,
    )
    if orig["source_entity_id"].duplicated().any():
        raise ValueError("duplicate origination Loan Identifier")
    orig["first_payment_ordinal"] = _period_to_ordinal(orig["first_payment_period"])
    return orig.set_index("source_entity_id", drop=False)


def _complete_groups(reader):
    """Yield frames containing only complete loan groups from a sorted stream."""
    carry: pd.DataFrame | None = None
    for chunk in reader:
        if carry is not None:
            chunk = pd.concat([carry, chunk], ignore_index=True)
            carry = None
        if chunk.empty:
            continue
        last_id = chunk["source_entity_id"].iloc[-1]
        mask = chunk["source_entity_id"].eq(last_id)
        carry = chunk.loc[mask].copy()
        complete = chunk.loc[~mask].copy()
        if not complete.empty:
            yield complete
    if carry is not None and not carry.empty:
        yield carry


def _aggregate_complete_frame(
    frame: pd.DataFrame,
    *,
    anchors: pd.DataFrame,
    protocol: TargetProtocol,
) -> pd.DataFrame:
    if frame.duplicated(["source_entity_id", "reporting_period"]).any():
        examples = frame.loc[
            frame.duplicated(["source_entity_id", "reporting_period"], keep=False),
            ["source_entity_id", "reporting_period"],
        ].head(10).to_dict("records")
        raise ValueError(f"duplicate Loan Identifier/reporting period pairs: {examples}")

    anchor_ord = frame["source_entity_id"].map(anchors["first_payment_ordinal"])
    if anchor_ord.isna().any():
        bad = frame.loc[anchor_ord.isna(), "source_entity_id"].head(10).tolist()
        raise ValueError(f"performance Loan Identifier missing origination anchor: {bad}")
    report_ord = _period_to_ordinal(frame["reporting_period"])
    frame = frame.copy()
    frame["payment_index"] = report_ord.to_numpy() - anchor_ord.astype("int64").to_numpy() + 1

    horizon = frame["payment_index"].between(protocol.horizon_min, protocol.horizon_max)
    status_num = pd.to_numeric(frame["delinquency_status"], errors="coerce")
    positive = horizon & (
        status_num.ge(protocol.serious_min_cycles)
        | frame["delinquency_status"].eq(protocol.reo_status)
        | frame["zero_balance_code"].isin(protocol.serious_zero_balance_codes)
    )
    unknown = horizon & (
        frame["delinquency_status"].eq(protocol.unknown_status)
        | frame["delinquency_status"].eq("")
    )

    # Sorted source means group order is deterministic.  Aggregation itself is
    # vectorized so ~20M monthly rows remain practical on a laptop.
    grouped = frame.groupby("source_entity_id", sort=False, observed=True)
    agg = grouped.agg(
        first_observed_payment_index=("payment_index", "min"),
        last_observed_payment_index=("payment_index", "max"),
        first_reporting_period=("reporting_period", "min"),
        last_reporting_period=("reporting_period", "max"),
    )
    agg["first_payment_period"] = agg.index.map(anchors["first_payment_period"])

    horizon_frame = frame.loc[horizon, ["source_entity_id", "payment_index"]].copy()
    horizon_frame["bit"] = np.left_shift(1, horizon_frame["payment_index"].to_numpy(dtype=np.int64) - 1)
    observed_mask = horizon_frame.groupby("source_entity_id", sort=False)["bit"].sum()
    agg["observed_mask"] = observed_mask.reindex(agg.index, fill_value=0).astype("int64")

    unknown_frame = frame.loc[unknown, ["source_entity_id", "payment_index"]].copy()
    if unknown_frame.empty:
        agg["unknown_mask"] = 0
    else:
        unknown_frame["bit"] = np.left_shift(1, unknown_frame["payment_index"].to_numpy(dtype=np.int64) - 1)
        unknown_mask = unknown_frame.groupby("source_entity_id", sort=False)["bit"].sum()
        agg["unknown_mask"] = unknown_mask.reindex(agg.index, fill_value=0).astype("int64")

    pos = frame.loc[positive, ["source_entity_id", "payment_index", "delinquency_status", "zero_balance_code"]].copy()
    if pos.empty:
        agg["event_payment_index"] = np.nan
        agg["target_event"] = ""
    else:
        pos["target_event"] = np.where(
            pos["zero_balance_code"].isin(protocol.serious_zero_balance_codes),
            "serious_zero_balance_" + pos["zero_balance_code"].astype(str),
            np.where(pos["delinquency_status"].eq(protocol.reo_status), "reo_status", "90plus_delinquency"),
        )
        pos = pos.sort_values(["source_entity_id", "payment_index"], kind="stable")
        first_pos = pos.groupby("source_entity_id", sort=False).first()
        agg["event_payment_index"] = first_pos["payment_index"].reindex(agg.index)
        agg["target_event"] = first_pos["target_event"].reindex(agg.index).fillna("")

    terminal = frame.loc[frame["zero_balance_code"].ne(""), ["source_entity_id", "payment_index", "zero_balance_code"]].copy()
    if terminal.empty:
        agg["terminal_payment_index"] = np.nan
        agg["terminal_zero_balance_code"] = ""
    else:
        terminal = terminal.sort_values(["source_entity_id", "payment_index"], kind="stable")
        first_terminal = terminal.groupby("source_entity_id", sort=False).first()
        agg["terminal_payment_index"] = first_terminal["payment_index"].reindex(agg.index)
        agg["terminal_zero_balance_code"] = first_terminal["zero_balance_code"].reindex(agg.index).fillna("")

    full_mask = (1 << protocol.horizon_max) - 1
    agg["observed_horizon_months"] = agg["observed_mask"].map(int.bit_count)
    is_positive = agg["event_payment_index"].notna()
    left_ok = agg["first_observed_payment_index"].le(protocol.horizon_min)
    through_horizon = agg["last_observed_payment_index"].ge(protocol.horizon_max)
    complete_horizon = agg["observed_mask"].eq(full_mask)
    known_horizon = agg["unknown_mask"].eq(0)

    terminal_idx = agg["terminal_payment_index"].fillna(10_000).astype(int)
    clean_payoff = agg["terminal_zero_balance_code"].isin(protocol.clean_negative_zero_balance_codes)
    required_masks = terminal_idx.clip(lower=0, upper=protocol.horizon_max).map(
        lambda n: (1 << int(n)) - 1 if n >= protocol.horizon_min else 0
    )
    payoff_complete = (agg["observed_mask"] & required_masks).eq(required_masks)
    payoff_known = (agg["unknown_mask"] & required_masks).eq(0)
    negative_full = (~is_positive) & left_ok & through_horizon & complete_horizon & known_horizon
    negative_payoff = (~is_positive) & left_ok & (~through_horizon) & clean_payoff & payoff_complete & payoff_known

    agg["target"] = pd.Series(pd.NA, index=agg.index, dtype="Int64")
    agg.loc[is_positive, "target"] = 1
    agg.loc[negative_full | negative_payoff, "target"] = 0
    agg["target_observation_status"] = np.where(agg["target"].isna(), "CENSORED", "ELIGIBLE")
    agg.loc[negative_full, "target_event"] = "no_serious_event_through_12m"
    agg.loc[negative_payoff, "target_event"] = "voluntary_payoff_before_12m"

    agg["censor_reason"] = ""
    censored = agg["target"].isna()
    agg.loc[censored & ~left_ok, "censor_reason"] = "left_censored_after_payment_month_1"
    remaining = censored & agg["censor_reason"].eq("")
    agg.loc[remaining & through_horizon & ~complete_horizon, "censor_reason"] = "missing_month_inside_12m_horizon"
    remaining = censored & agg["censor_reason"].eq("")
    agg.loc[remaining & through_horizon & complete_horizon & ~known_horizon, "censor_reason"] = "unknown_delinquency_inside_12m_horizon"
    remaining = censored & agg["censor_reason"].eq("")
    agg.loc[remaining & clean_payoff & ~payoff_complete, "censor_reason"] = "missing_month_before_voluntary_payoff"
    remaining = censored & agg["censor_reason"].eq("")
    agg.loc[remaining & clean_payoff & payoff_complete & ~payoff_known, "censor_reason"] = "unknown_status_before_voluntary_payoff"
    remaining = censored & agg["censor_reason"].eq("")
    for code in protocol.censoring_zero_balance_codes:
        hit = remaining & agg["terminal_zero_balance_code"].eq(code)
        agg.loc[hit, "censor_reason"] = f"non_outcome_termination_{code}"
        remaining = censored & agg["censor_reason"].eq("")
    agg.loc[remaining, "censor_reason"] = "insufficient_12m_observation"

    result = agg.reset_index().rename(columns={"source_entity_id": "source_entity_id"})
    return result[list(TARGET_COLUMNS)]


def _parse_yyyymm_bytes(value: bytes, *, field: str) -> tuple[str, int]:
    raw = value.strip()
    if len(raw) != 6 or not raw.isdigit():
        raise ValueError(f"invalid {field} YYYYMM value: {raw!r}")
    year = int(raw[:4])
    month = int(raw[4:6])
    if month < 1 or month > 12:
        raise ValueError(f"invalid {field} YYYYMM value: {raw!r}")
    text = raw.decode("ascii")
    return text, year * 12 + month


def _load_anchor_map(stream) -> dict[bytes, tuple[str, int]]:
    """Load only Loan Identifier -> First Payment Date for one vintage quarter."""
    anchors: dict[bytes, tuple[str, int]] = {}
    for row_number, raw_line in enumerate(stream, start=1):
        # Need columns 2 and 20 (1-based).  Stop tokenizing after Loan ID.
        values = raw_line.rstrip(b"\r\n").split(b"|", 20)
        if len(values) <= 19:
            raise ValueError(f"origination row {row_number}: fewer than 20 fields")
        loan_id = values[19].strip()
        if not loan_id:
            raise ValueError(f"origination row {row_number}: blank Loan Identifier")
        if loan_id in anchors:
            raise ValueError(f"duplicate origination Loan Identifier: {loan_id!r}")
        first_payment_text, first_payment_ordinal = _parse_yyyymm_bytes(
            values[1], field="First Payment Date"
        )
        anchors[loan_id] = (first_payment_text, first_payment_ordinal)
    return anchors


def _delinquency_is_serious(status: str, protocol: TargetProtocol) -> bool:
    if status == protocol.reo_status:
        return True
    if status.isdigit():
        return int(status) >= protocol.serious_min_cycles
    return False


def _finalize_streamed_loan(
    *,
    loan_id: bytes,
    first_payment_period: str,
    first_observed_payment_index: int,
    last_observed_payment_index: int,
    first_reporting_period: str,
    last_reporting_period: str,
    observed_mask: int,
    unknown_mask: int,
    event_payment_index: int | None,
    target_event: str,
    terminal_zero_balance_code: str,
    terminal_payment_index: int | None,
    protocol: TargetProtocol,
) -> tuple[list[Any], str, str, str]:
    """Return one target CSV row plus accounting labels.

    The logic mirrors the vectorized reference implementation but runs on a
    single loan state.  Positive evidence is conclusive even when earlier
    performance is left-censored; negatives require complete observation.
    """
    full_mask = (1 << protocol.horizon_max) - 1
    observed_horizon_months = int(observed_mask).bit_count()
    is_positive = event_payment_index is not None
    left_ok = first_observed_payment_index <= protocol.horizon_min
    through_horizon = last_observed_payment_index >= protocol.horizon_max
    complete_horizon = observed_mask == full_mask
    known_horizon = unknown_mask == 0

    terminal_idx = terminal_payment_index if terminal_payment_index is not None else 10_000
    clean_payoff = terminal_zero_balance_code in protocol.clean_negative_zero_balance_codes
    clipped_terminal = min(max(terminal_idx, 0), protocol.horizon_max)
    required_mask = (1 << clipped_terminal) - 1 if clipped_terminal >= protocol.horizon_min else 0
    payoff_complete = (observed_mask & required_mask) == required_mask
    payoff_known = (unknown_mask & required_mask) == 0

    negative_full = (
        (not is_positive)
        and left_ok
        and through_horizon
        and complete_horizon
        and known_horizon
    )
    negative_payoff = (
        (not is_positive)
        and left_ok
        and (not through_horizon)
        and clean_payoff
        and payoff_complete
        and payoff_known
    )

    target: int | None
    status: str
    censor_reason = ""
    if is_positive:
        target = 1
        status = "ELIGIBLE"
    elif negative_full:
        target = 0
        status = "ELIGIBLE"
        target_event = "no_serious_event_through_12m"
    elif negative_payoff:
        target = 0
        status = "ELIGIBLE"
        target_event = "voluntary_payoff_before_12m"
    else:
        target = None
        status = "CENSORED"
        if not left_ok:
            censor_reason = "left_censored_after_payment_month_1"
        elif through_horizon and not complete_horizon:
            censor_reason = "missing_month_inside_12m_horizon"
        elif through_horizon and complete_horizon and not known_horizon:
            censor_reason = "unknown_delinquency_inside_12m_horizon"
        elif clean_payoff and not payoff_complete:
            censor_reason = "missing_month_before_voluntary_payoff"
        elif clean_payoff and payoff_complete and not payoff_known:
            censor_reason = "unknown_status_before_voluntary_payoff"
        elif terminal_zero_balance_code in protocol.censoring_zero_balance_codes:
            censor_reason = f"non_outcome_termination_{terminal_zero_balance_code}"
        else:
            censor_reason = "insufficient_12m_observation"

    row = [
        loan_id.decode("ascii"),
        "" if target is None else target,
        status,
        target_event,
        first_payment_period,
        first_observed_payment_index,
        last_observed_payment_index,
        "" if event_payment_index is None else event_payment_index,
        terminal_zero_balance_code,
        "" if terminal_payment_index is None else terminal_payment_index,
        observed_horizon_months,
        first_reporting_period,
        last_reporting_period,
        censor_reason,
    ]
    event_label = target_event if target is not None else ""
    return row, status, event_label, censor_reason


def _process_quarter(
    nested: zipfile.ZipFile,
    quarter: str,
    protocol: TargetProtocol,
    target_path: Path,
) -> dict[str, Any]:
    """Stream one quarter with O(number-of-origination-loans) anchor memory.

    No pandas parser is used on the ~20M-row production performance scan.  The
    Freddie file is already certified as grouped by Loan Identifier at M11, so
    one small loan state is sufficient while streaming monthly rows.
    """
    with nested.open(f"orig_{quarter}.txt") as orig_stream:
        anchors = _load_anchor_map(orig_stream)

    target_path.unlink(missing_ok=True)
    temporary_target = target_path.with_name(f".{target_path.name}.tmp")
    temporary_target.unlink(missing_ok=True)

    performance_rows = 0
    loan_rows = eligible = positive = negative = censored = 0
    event_counts: dict[str, int] = {}
    censor_counts: dict[str, int] = {}

    current_id: bytes | None = None
    current_anchor: tuple[str, int] | None = None
    first_idx = last_idx = 0
    first_period = last_period = ""
    observed_mask = unknown_mask = 0
    event_idx: int | None = None
    event_label = ""
    terminal_code = ""
    terminal_idx: int | None = None
    previous_period_ordinal: int | None = None

    def flush(writer: csv.writer) -> None:
        nonlocal loan_rows, eligible, positive, negative, censored
        nonlocal current_id, current_anchor, first_idx, last_idx, first_period, last_period
        nonlocal observed_mask, unknown_mask, event_idx, event_label, terminal_code, terminal_idx
        if current_id is None or current_anchor is None:
            return
        row, observation_status, final_event, censor_reason = _finalize_streamed_loan(
            loan_id=current_id,
            first_payment_period=current_anchor[0],
            first_observed_payment_index=first_idx,
            last_observed_payment_index=last_idx,
            first_reporting_period=first_period,
            last_reporting_period=last_period,
            observed_mask=observed_mask,
            unknown_mask=unknown_mask,
            event_payment_index=event_idx,
            target_event=event_label,
            terminal_zero_balance_code=terminal_code,
            terminal_payment_index=terminal_idx,
            protocol=protocol,
        )
        writer.writerow(row)
        loan_rows += 1
        if observation_status == "ELIGIBLE":
            eligible += 1
            if row[1] == 1:
                positive += 1
            elif row[1] == 0:
                negative += 1
            event_counts[final_event] = event_counts.get(final_event, 0) + 1
        else:
            censored += 1
            censor_counts[censor_reason] = censor_counts.get(censor_reason, 0) + 1

    with temporary_target.open("w", newline="", encoding="utf-8") as target_handle:
        writer = csv.writer(target_handle, lineterminator="\n")
        writer.writerow(TARGET_COLUMNS)
        with nested.open(f"perf_{quarter}.txt") as perf_stream:
            for row_number, raw_line in enumerate(perf_stream, start=1):
                performance_rows += 1
                # Need only columns 1, 2, 4 and 9 (1-based).
                values = raw_line.rstrip(b"\r\n").split(b"|", 9)
                if len(values) <= 8:
                    raise ValueError(f"{quarter} performance row {row_number}: fewer than 9 fields")
                loan_id = values[0].strip()
                period_text, period_ordinal = _parse_yyyymm_bytes(
                    values[1], field="Monthly Reporting Period"
                )
                status = values[3].strip().decode("ascii")
                zbc = values[8].strip().decode("ascii")

                if current_id != loan_id:
                    if current_id is not None:
                        if loan_id < current_id:
                            raise ValueError("performance file is not sorted/grouped by Loan Identifier")
                        flush(writer)
                    current_id = loan_id
                    current_anchor = anchors.get(loan_id)
                    if current_anchor is None:
                        raise ValueError(f"performance Loan Identifier missing origination anchor: {loan_id!r}")
                    first_idx = last_idx = period_ordinal - current_anchor[1] + 1
                    first_period = last_period = period_text
                    observed_mask = unknown_mask = 0
                    event_idx = None
                    event_label = ""
                    terminal_code = ""
                    terminal_idx = None
                    previous_period_ordinal = None

                if previous_period_ordinal is not None and period_ordinal <= previous_period_ordinal:
                    if period_ordinal == previous_period_ordinal:
                        raise ValueError(
                            f"duplicate Loan Identifier/reporting period pair: {loan_id.decode('ascii')}/{period_text}"
                        )
                    raise ValueError(
                        f"non-increasing Monthly Reporting Period for {loan_id.decode('ascii')}: {last_period} -> {period_text}"
                    )
                previous_period_ordinal = period_ordinal

                assert current_anchor is not None
                idx = period_ordinal - current_anchor[1] + 1
                # first_idx was initialized when the Loan Identifier changed.
                last_idx = idx
                last_period = period_text

                if protocol.horizon_min <= idx <= protocol.horizon_max:
                    bit = 1 << (idx - 1)
                    observed_mask |= bit
                    if status == protocol.unknown_status or status == "":
                        unknown_mask |= bit
                    serious_zbc = zbc in protocol.serious_zero_balance_codes
                    serious = _delinquency_is_serious(status, protocol) or serious_zbc
                    if serious and (event_idx is None or idx < event_idx):
                        event_idx = idx
                        if serious_zbc:
                            event_label = f"serious_zero_balance_{zbc}"
                        elif status == protocol.reo_status:
                            event_label = "reo_status"
                        else:
                            event_label = "90plus_delinquency"

                if zbc and terminal_idx is None:
                    terminal_code = zbc
                    terminal_idx = idx

            flush(writer)

    if loan_rows != len(anchors):
        temporary_target.unlink(missing_ok=True)
        raise ValueError(f"target loan count differs from origination count: {loan_rows} != {len(anchors)}")
    temporary_target.replace(target_path)
    return {
        "quarter": quarter,
        "performance_rows": performance_rows,
        "loans": loan_rows,
        "eligible": eligible,
        "positive": positive,
        "negative": negative,
        "censored": censored,
        "event_counts": dict(sorted(event_counts.items())),
        "censor_reason_counts": dict(sorted(censor_counts.items())),
    }


@dataclass(frozen=True)
class TargetBuildResult:
    target_path: Path
    manifest_path: Path
    receipt_path: Path
    manifest: dict[str, Any]
    receipt: StageReceipt


class FreddieTargetBuilder:
    def __init__(self, *, raw_zip: Path, protocol_path: Path, m11_dir: Path) -> None:
        self.raw_zip = raw_zip.expanduser().resolve()
        self.protocol_path = protocol_path.expanduser().resolve()
        self.m11_dir = m11_dir.expanduser().resolve()
        self.protocol = TargetProtocol.load(self.protocol_path)

    def _verify_m11(self) -> StageReceipt:
        receipt_path = self.m11_dir / "freddie_sflld_2024_m11_receipt_v1.json"
        receipt = load_receipt(receipt_path)
        raw_sha = sha256_path(self.raw_zip)
        if receipt.stage != "freddie_sflld_raw_intake" or receipt.status != "PASS":
            raise ValueError("valid M11 raw-intake receipt is required")
        if receipt.input_fingerprints.get("raw_source") != raw_sha:
            raise ValueError("M11 receipt raw-source hash does not match target-builder input")
        for name, expected_hash in receipt.output_fingerprints.items():
            path = self.m11_dir / name
            if not path.is_file() or sha256_path(path) != expected_hash:
                raise ValueError(f"M11 evidence invalid or modified: {name}")
        return receipt

    def run_quarter(self, output_dir: Path, quarter: str) -> dict[str, Any]:
        """Build exactly one deterministic quarter partition.

        A worker process should call this method and then exit.  The raw
        performance scan is streaming/bounded-memory; process isolation makes
        the four-quarter build resumable and keeps decompressor/allocator state
        scoped to one quarter.
        """
        if quarter not in QUARTERS:
            raise ValueError(f"unsupported quarter: {quarter}")
        self._verify_m11()
        output_dir = output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        target_path = output_dir / f"freddie_target_12m_{quarter}_v1.csv"
        stats_path = output_dir / f"freddie_target_12m_{quarter}_stats_v1.json"

        with zipfile.ZipFile(self.raw_zip) as outer, tempfile.TemporaryDirectory(
            prefix=f"freddie_target_{quarter}_"
        ) as td:
            nested_path = Path(td) / f"{quarter}.zip"
            with outer.open(f"historical_data_{quarter}.zip") as source, nested_path.open("wb") as dest:
                nested_sha = _hash_copy(source, dest)
            with zipfile.ZipFile(nested_path) as nested:
                stats = _process_quarter(nested, quarter, self.protocol, target_path)

        payload = {
            "schema_version": "freddie_target_quarter_stats_v1",
            "dataset_id": DATASET_ID,
            "target_id": self.protocol.target_id,
            "quarter": quarter,
            "raw_source_sha256": sha256_path(self.raw_zip),
            "target_protocol_sha256": sha256_path(self.protocol_path),
            "nested_zip_sha256": nested_sha,
            "target_partition": {
                "filename": target_path.name,
                "sha256": sha256_path(target_path),
                "rows": int(stats["loans"]),
            },
            "stats": stats,
        }
        write_json_atomic(stats_path, payload)
        return payload

    def finalize(self, output_dir: Path) -> TargetBuildResult:
        """Certify four existing quarter partitions without rebuilding them."""
        m11_receipt = self._verify_m11()
        output_dir = output_dir.expanduser().resolve()
        raw_sha = sha256_path(self.raw_zip)
        protocol_sha = sha256_path(self.protocol_path)
        quarter_stats: list[dict[str, Any]] = []
        partition_payloads: list[dict[str, Any]] = []
        quarter_artifacts: list[dict[str, str]] = []

        for quarter in QUARTERS:
            stats_path = output_dir / f"freddie_target_12m_{quarter}_stats_v1.json"
            if not stats_path.is_file():
                raise FileNotFoundError(f"missing quarter stats: {stats_path}")
            payload = json.loads(stats_path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != "freddie_target_quarter_stats_v1":
                raise ValueError(f"{quarter}: unsupported quarter stats schema")
            if payload.get("quarter") != quarter or payload.get("dataset_id") != DATASET_ID:
                raise ValueError(f"{quarter}: quarter stats identity mismatch")
            if payload.get("raw_source_sha256") != raw_sha:
                raise ValueError(f"{quarter}: raw source fingerprint mismatch")
            if payload.get("target_protocol_sha256") != protocol_sha:
                raise ValueError(f"{quarter}: target protocol fingerprint mismatch")
            partition = payload["target_partition"]
            partition_path = output_dir / partition["filename"]
            if not partition_path.is_file() or sha256_path(partition_path) != partition["sha256"]:
                raise ValueError(f"{quarter}: target partition missing or modified")
            if int(partition["rows"]) != int(payload["stats"]["loans"]):
                raise ValueError(f"{quarter}: partition/stats row-count mismatch")
            quarter_stats.append(payload["stats"])
            partition_payloads.append({"quarter": quarter, **partition})
            quarter_artifacts.append({
                "quarter": quarter,
                "stats_filename": stats_path.name,
                "stats_sha256": sha256_path(stats_path),
            })

        totals = {
            key: sum(int(q[key]) for q in quarter_stats)
            for key in ("performance_rows", "loans", "eligible", "positive", "negative", "censored")
        }
        totals["positive_rate_eligible"] = totals["positive"] / totals["eligible"]
        events: dict[str, int] = {}
        censors: dict[str, int] = {}
        for q in quarter_stats:
            for key, value in q["event_counts"].items():
                events[key] = events.get(key, 0) + int(value)
            for key, value in q["censor_reason_counts"].items():
                censors[key] = censors.get(key, 0) + int(value)

        manifest = {
            "schema_version": "freddie_target_manifest_v1",
            "dataset_id": DATASET_ID,
            "target_id": self.protocol.target_id,
            "horizon_anchor": "origination_first_payment_date",
            "raw_loan_age_used_for_horizon": False,
            "raw_source_sha256": raw_sha,
            "target_protocol_sha256": protocol_sha,
            "m11_receipt_fingerprint": m11_receipt.receipt_fingerprint,
            "quarter_stats": quarter_stats,
            "quarter_artifacts": quarter_artifacts,
            "totals": totals,
            "event_counts": dict(sorted(events.items())),
            "censor_reason_counts": dict(sorted(censors.items())),
            "target_partitions": partition_payloads,
            "target_columns": list(TARGET_COLUMNS),
        }
        manifest_path = output_dir / "freddie_target_12m_manifest_v1.json"
        write_json_atomic(manifest_path, manifest)

        invariants = {
            "m11_receipt_verified": "PASS",
            "horizon_anchored_to_origination_first_payment": "PASS",
            "raw_loan_age_not_used_for_horizon": "PASS",
            "all_performance_rows_consumed": "PASS",
            "one_target_record_per_loan": "PASS",
            "target_values_binary_or_censored": "PASS",
            "quarter_partitions_complete": "PASS" if len(partition_payloads) == len(QUARTERS) else "FAIL",
            "positive_target_nonempty": "PASS" if totals["positive"] else "FAIL",
            "negative_target_nonempty": "PASS" if totals["negative"] else "FAIL",
        }
        if any(value != "PASS" for value in invariants.values()):
            raise ValueError(f"target-builder invariant failed: {invariants}")

        output_fingerprints: dict[str, str] = {
            item["filename"]: item["sha256"] for item in partition_payloads
        }
        for item in quarter_artifacts:
            output_fingerprints[item["stats_filename"]] = item["stats_sha256"]
        output_fingerprints[manifest_path.name] = sha256_path(manifest_path)
        receipt = StageReceipt(
            stage=TARGET_STAGE,
            stage_version=TARGET_STAGE_VERSION,
            dataset_id=DATASET_ID,
            patch_id=PATCH_ID,
            input_fingerprints={
                "raw_source": raw_sha,
                "m11_receipt": sha256_path(self.m11_dir / "freddie_sflld_2024_m11_receipt_v1.json"),
            },
            config_fingerprints={"target_protocol": protocol_sha},
            output_fingerprints=output_fingerprints,
            invariants=invariants,
        )
        receipt_path = output_dir / "freddie_sflld_2024_m12a_target_receipt_v1.json"
        write_json_atomic(receipt_path, receipt.to_dict())
        return TargetBuildResult(manifest_path, manifest_path, receipt_path, manifest, receipt)

    def run(self, output_dir: Path) -> TargetBuildResult:
        """In-process helper used by tests/small fixtures only.

        Production CLI orchestrates one OS process per quarter and then calls
        :meth:`finalize`, which bounds allocator/parser state for ~20M rows.
        """
        for quarter in QUARTERS:
            self.run_quarter(output_dir, quarter)
        return self.finalize(output_dir)
