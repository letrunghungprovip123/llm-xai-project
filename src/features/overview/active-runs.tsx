import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { StatusTag } from "@/components/common/status-tag";
import { SectionHeader } from "@/components/ui/section-header";
import type { RunSummary } from "@/lib/api/contracts";
import { duration, relativeTime } from "@/lib/format";

export function ActiveRuns({ runs, loading, unavailable }: { runs: RunSummary[]; loading?: boolean; unavailable?: boolean }) {
  return (
    <section>
      <SectionHeader
        title="Active runs"
        description="Pipeline executions currently in progress."
        action={<Link href="/runs?status=RUNNING" className="text-[13px] font-medium text-[var(--color-brand)] hover:underline">View all runs</Link>}
      />
      <div className="panel mt-3 overflow-hidden">
        {unavailable ? (
          <div className="px-5 py-8 text-center text-[13px] text-[var(--color-warning)]">Active runs are temporarily unavailable.</div>
        ) : loading && !runs.length ? (
          <div className="space-y-3 p-4" aria-label="Loading active runs">
            {[0, 1, 2].map((item) => <div key={item} className="h-12 animate-pulse rounded-lg bg-[var(--color-surface-subtle)]" />)}
          </div>
        ) : runs.length ? (
          <div className="divide-y divide-[var(--color-border)]">
            {runs.map((run) => (
              <Link
                key={run.id}
                href={`/runs/${encodeURIComponent(run.id)}`}
                className="group flex min-h-[72px] items-center gap-3 px-4 py-3 transition hover:bg-[var(--color-surface-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand)]"
              >
                <StatusTag value={run.status} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-semibold text-[var(--color-text)]">{run.flow_id}</span>
                  <span className="mt-0.5 block truncate font-mono text-[11px] text-[var(--color-text-muted)]">{run.id}</span>
                </span>
                <span className="hidden text-right sm:block">
                  <span className="block text-[12px] text-[var(--color-text-secondary)]">{duration(run.started_at, run.ended_at)}</span>
                  <span className="mt-0.5 block text-[11px] text-[var(--color-text-muted)]">Started {relativeTime(run.started_at)}</span>
                </span>
                <ArrowRight size={15} className="text-[var(--color-text-muted)] transition group-hover:translate-x-0.5 group-hover:text-[var(--color-brand)]" aria-hidden="true" />
              </Link>
            ))}
          </div>
        ) : (
          <div className="px-5 py-8 text-center">
            <p className="text-[14px] font-medium text-[var(--color-text)]">No runs are active</p>
            <p className="mt-1 text-[12px] text-[var(--color-text-muted)]">Running pipeline executions will appear here.</p>
          </div>
        )}
      </div>
    </section>
  );
}
