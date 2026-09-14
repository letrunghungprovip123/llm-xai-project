import Link from "next/link";
import { ArrowRight, Box } from "lucide-react";
import type { RunOutputView } from "@/lib/api/contracts";
import { relativeTime } from "@/lib/format";

export function RunOutputs({ outputs, loading, unavailable }: { outputs: RunOutputView[]; loading?: boolean; unavailable?: boolean }) {
  if (unavailable) return <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-5 text-[13px] text-[var(--color-warning)]">Run outputs are temporarily unavailable.</div>;
  if (loading && !outputs.length) return <div className="space-y-2">{[0, 1, 2].map((item) => <div key={item} className="h-14 animate-pulse rounded-lg bg-[var(--color-surface-subtle)]" />)}</div>;
  if (!outputs.length) return <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-5 text-[13px] text-[var(--color-text-muted)]">This run has no registered outputs yet.</div>;

  return (
    <div className="divide-y divide-[var(--color-border)] rounded-[var(--radius-lg)] border border-[var(--color-border)]">
      {outputs.map((output) => (
        <Link
          key={`${output.stage_run_id}:${output.output_name}:${output.artifact_id}`}
          href={`/artifacts/${encodeURIComponent(output.artifact_id)}`}
          className="group flex min-h-[64px] items-center gap-3 px-4 py-3 transition hover:bg-[var(--color-surface-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand)]"
        >
          <Box size={16} className="shrink-0 text-[var(--color-text-muted)]" aria-hidden="true" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-semibold text-[var(--color-text)]">{output.output_name}</span>
            <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[var(--color-text-muted)]">
              <span>{output.artifact_type}</span><span aria-hidden="true">·</span><span className="max-w-[260px] truncate font-mono" title={output.artifact_id}>{output.artifact_id}</span>
            </span>
          </span>
          <span className="hidden shrink-0 text-[11px] text-[var(--color-text-muted)] sm:block">{relativeTime(output.created_at)}</span>
          <ArrowRight size={15} className="shrink-0 text-[var(--color-text-muted)] transition group-hover:translate-x-0.5 group-hover:text-[var(--color-brand)]" aria-hidden="true" />
        </Link>
      ))}
    </div>
  );
}
