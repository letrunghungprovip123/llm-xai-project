from __future__ import annotations

from uuid import UUID

import pytest

from research.python.researchops.orchestration.approvals.cli import (
    PrefectResumeReadinessTimeout,
    parser,
    resume_prefect_flow_run,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def test_resume_supplies_declared_run_input_and_retries_schema_publication():
    flow_run_id = UUID("11111111-1111-1111-1111-111111111111")
    run_input = {
        "approval_id": "approval_1",
        "acknowledgement": "decision-recorded",
    }
    calls: list[tuple[UUID, dict[str, str]]] = []
    clock = FakeClock()

    def resume(candidate: UUID, *, run_input: dict[str, str]) -> None:
        calls.append((candidate, run_input))
        if len(calls) < 3:
            raise RuntimeError("Cannot resume this run: Run input schema not found.")

    report = resume_prefect_flow_run(
        flow_run_id,
        run_input=run_input,
        timeout_seconds=5,
        poll_interval_seconds=0.25,
        resume_callable=resume,
        sleep_callable=clock.sleep,
        clock_callable=clock.now,
    )

    assert calls == [(flow_run_id, run_input)] * 3
    assert report == {
        "flow_run_id": str(flow_run_id),
        "resumed": True,
        "attempt_count": 3,
        "readiness_retries": 2,
        "schema_wait_retries": 2,
        "elapsed_seconds": 0.5,
    }


def test_resume_retries_exact_prefect_not_paused_readiness_error():
    flow_run_id = UUID("22222222-2222-2222-2222-222222222222")
    clock = FakeClock()
    calls: list[UUID] = []

    NotPausedError = type("NotPausedError", (RuntimeError,), {})
    NotPausedError.__module__ = "prefect.exceptions"

    def resume(candidate: UUID, *, run_input: dict[str, str]) -> None:
        del run_input
        calls.append(candidate)
        if len(calls) == 1:
            raise NotPausedError("Cannot resume a run that isn't paused!")

    report = resume_prefect_flow_run(
        flow_run_id,
        run_input={"approval_id": "approval_2"},
        timeout_seconds=5,
        poll_interval_seconds=0.5,
        resume_callable=resume,
        sleep_callable=clock.sleep,
        clock_callable=clock.now,
    )

    assert calls == [flow_run_id, flow_run_id]
    assert report["readiness_retries"] == 1


def test_resume_fails_closed_for_non_transient_prefect_rejection():
    def resume(candidate: UUID, *, run_input: dict[str, str]) -> None:
        del candidate, run_input
        raise RuntimeError("Cannot resume this run: approval input is invalid")

    with pytest.raises(RuntimeError, match="approval input is invalid"):
        resume_prefect_flow_run(
            "33333333-3333-3333-3333-333333333333",
            run_input={"approval_id": "approval_3"},
            resume_callable=resume,
        )


def test_resume_timeout_preserves_authoritative_decision_for_manual_recovery():
    clock = FakeClock()

    def resume(candidate: UUID, *, run_input: dict[str, str]) -> None:
        del candidate, run_input
        raise RuntimeError("Cannot resume this run: Run input schema not found.")

    with pytest.raises(
        PrefectResumeReadinessTimeout,
        match="approval decision remains authoritative in Ops DB",
    ):
        resume_prefect_flow_run(
            "44444444-4444-4444-4444-444444444444",
            run_input={"approval_id": "approval_4"},
            timeout_seconds=1,
            poll_interval_seconds=0.4,
            resume_callable=resume,
            sleep_callable=clock.sleep,
            clock_callable=clock.now,
        )


def test_resume_requires_non_empty_input_and_valid_timing():
    with pytest.raises(ValueError, match="run_input"):
        resume_prefect_flow_run(
            "55555555-5555-5555-5555-555555555555",
            run_input={},
            resume_callable=lambda *args, **kwargs: None,
        )
    with pytest.raises(ValueError, match="timeout_seconds"):
        resume_prefect_flow_run(
            "66666666-6666-6666-6666-666666666666",
            run_input={"approval_id": "approval_6"},
            timeout_seconds=-1,
            resume_callable=lambda *args, **kwargs: None,
        )
    with pytest.raises(ValueError, match="poll_interval_seconds"):
        resume_prefect_flow_run(
            "77777777-7777-7777-7777-777777777777",
            run_input={"approval_id": "approval_7"},
            poll_interval_seconds=0,
            resume_callable=lambda *args, **kwargs: None,
        )


def test_resume_command_supports_recovering_an_already_decided_approval():
    args = parser().parse_args(
        [
            "resume",
            "--approval-id",
            "approval_8",
            "--resume-timeout-seconds",
            "12",
            "--resume-poll-interval-seconds",
            "0.2",
        ]
    )

    assert args.command == "resume"
    assert args.approval_id == "approval_8"
    assert args.resume_timeout_seconds == 12
    assert args.resume_poll_interval_seconds == 0.2
