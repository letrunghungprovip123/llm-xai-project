import { AlertTriangle, CheckCircle2, Circle, Clock3, LoaderCircle, XCircle } from "lucide-react";
import { StatusTag } from "@/components/common/status-tag";
import type { StageRunView } from "@/lib/api/contracts";
import { dateTime, duration } from "@/lib/format";

function StageIcon({ status }: { status: string }) {
  if (status === "SUCCEEDED") return <CheckCircle2 size={18} className="text-[var(--color-success)]" aria-hidden="true" />;
  if (status === "RUNNING") return <LoaderCircle size={18} className="text-[var(--color-info)]" aria-hidden="true" />;
  if (status === "FAILED") return <AlertTriangle size={18} className="text-[var(--color-danger)]" aria-hidden="true" />;
  if (status === "WAITING_APPROVAL") return <Clock3 size={18} className="text-[var(--color-warning)]" aria-hidden="true" />;
  if (status === "CANCELLED") return <XCircle size={18} className="text-[var(--color-text-muted)]" aria-hidden="true" />;
  return <Circle size={18} className="text-[var(--color-text-muted)]" aria-hidden="true" />;
}

export function StageTimeline({ stages, loading, unavailable }: { stages: StageRunView[]; loading?: boolean; unavailable?: boolean }) {
  if (unavailable) return <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-5 text-[13px] text-[var(--color-warning)]">Pipeline stages are temporarily unavailable.</div>;
  if (loading && !stages.length) return <div className="space-y-3">{[0, 1, 2, 3].map((item) => <div key={item} className="h-16 animate-pulse rounded-lg bg-[var(--color-surface-subtle)]" />)}</div>;
  if (!stages.length) return <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-5 text-[13px] text-[var(--color-text-muted)]">No stage executions have been registered for this run yet.</div>;

  return (
    <ol className="relative ml-2 border-l border-[var(--color-border-strong)]">
      {stages.map((stage, index) => (
        <li key={stage.id} className={index === stages.length - 1 ? "relative pb-1 pl-7" : "relative pb-6 pl-7"}>
          <span className="absolute -left-[10px] top-0 flex h-5 w-5 items-center justify-center bg-[var(--color-surface)]">
            <StageIcon status={stage.status} />
          </span>
          <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="truncate text-[14px] font-semibold text-[var(--color-text)]">{stage.stage_id}</h3>
                  <StatusTag value={stage.status} />
                </div>
                <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">v{stage.stage_version} · attempt {stage.attempt} · approval policy {stage.approval_policy}</p>
              </div>
              <div className="shrink-0 text-left text-[11px] text-[var(--color-text-muted)] sm:text-right">
                <div>{duration(stage.started_at, stage.ended_at)}</div>
                <div className="mt-0.5">{stage.started_at ? dateTime(stage.started_at) : "Not started"}</div>
              </div>
            </div>
            {stage.error_message ? (
              <div className="mt-3 rounded-lg bg-[var(--color-surface-subtle)] px-3 py-2 text-[12px] leading-5 text-[var(--color-danger)]">
                {stage.error_type ? <span className="font-semibold">{stage.error_type}: </span> : null}{stage.error_message}
              </div>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
