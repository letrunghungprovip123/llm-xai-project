# Prefect approval boundaries and reconciliation

## Approval operations

List pending approvals:

```bash
python3 -m research.python.researchops.orchestration.approvals list \
  --status REQUESTED
```

Approve and then resume the suspended Prefect flow:

```bash
python3 -m research.python.researchops.orchestration.approvals approve \
  --approval-id "$APPROVAL_ID" \
  --actor reviewer@example.local \
  --reason "Reviewed inputs, cost and release scope" \
  --resume-prefect
```

The command writes the decision and audit event before it calls Prefect resume.
The flow re-validates the approval from PostgreSQL after resumption.

## Reconciliation

```bash
python3 -m research.python.researchops.orchestration.reconciliation \
  --mode report-only \
  --report-path /tmp/prefect-ops-reconciliation.json
```

Use `repair-safe` only after reviewing the report. Safe repair is intentionally
limited to stale approval expiry and uniquely verified terminal failure/cancellation
state. It never deletes or promotes anything.

## Resume-input readiness boundary

The Ops approval decision is committed before Prefect is resumed. This preserves the
Ops database as the authoritative audit record even if the orchestration API is
temporarily unavailable.

Prefect's `suspend_flow_run(wait_for_input=...)` transitions the run to a paused
state before the run-input schema is persisted. A reviewer or automated acceptance
client can observe the approval row during that narrow publication interval. The
approval CLI therefore retries only the exact transient rejection
`Run input schema not found` with a bounded timeout. All other Prefect resume errors
fail closed immediately.

A committed decision is never rolled back when the bounded resume attempt fails.
The explicit recovery command is:

```bash
python -m research.python.researchops.orchestration.approvals resume \
  --approval-id <approval_id>
```

This command is restricted to `APPROVED` or `REJECTED` records and reuses the
original immutable decision metadata.
