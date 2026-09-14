import { Activity } from "lucide-react";
import { JsonView } from "@/components/common/json-view";
import type { RunEventView } from "@/lib/api/contracts";
import { dateTime, relativeTime } from "@/lib/format";

export function RunActivity({ events, loading, unavailable, limit = 8 }: { events: RunEventView[]; loading?: boolean; unavailable?: boolean; limit?: number }) {
  if (unavailable) return <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-5 text-[13px] text-[var(--color-warning)]">Run activity could not be loaded.</div>;
  if (loading && !events.length) return <div className="space-y-2">{[0, 1, 2].map((item) => <div key={item} className="h-12 animate-pulse rounded-lg bg-[var(--color-surface-subtle)]" />)}</div>;
  const latest = [...events].reverse().slice(0, limit);
  if (!latest.length) return <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-5 text-[13px] text-[var(--color-text-muted)]">No run activity has been recorded yet.</div>;

  return (
    <div className="divide-y divide-[var(--color-border)] rounded-[var(--radius-lg)] border border-[var(--color-border)]">
      {latest.map((event) => (
        <details key={event.id} className="group px-4 py-3">
          <summary className="flex cursor-pointer list-none items-center gap-3 outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]">
            <Activity size={15} className="shrink-0 text-[var(--color-info)]" aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-[var(--color-text)]">{event.event_type}</span>
            <span className="hidden shrink-0 text-[11px] text-[var(--color-text-muted)] sm:block" title={dateTime(event.occurred_at)}>{relativeTime(event.occurred_at)}</span>
          </summary>
          <div className="mt-3 pl-7">
            <p className="mb-2 text-[11px] text-[var(--color-text-muted)]">{dateTime(event.occurred_at)}{event.stage_run_id ? ` · stage run ${event.stage_run_id}` : ""}</p>
            <JsonView value={event.payload} maxHeight={220} />
          </div>
        </details>
      ))}
    </div>
  );
}
