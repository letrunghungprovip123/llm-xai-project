import Link from "next/link";
import { AlertCircle, ArrowRight, CircleAlert, Clock3 } from "lucide-react";
import { SectionHeader } from "@/components/ui/section-header";
import { relativeTime } from "@/lib/format";

export type AttentionItem = {
  id: string;
  kind: "gate" | "operation" | "approval";
  title: string;
  description: string;
  timestamp: string | null;
  href: string;
};

const iconByKind = {
  gate: CircleAlert,
  operation: AlertCircle,
  approval: Clock3,
} as const;

export function AttentionQueue({ items, unavailable = [], loading = false }: { items: AttentionItem[]; unavailable?: string[]; loading?: boolean }) {
  return (
    <section>
      <SectionHeader
        title="Needs attention"
        description="Blocking governance signals and control actions that may require intervention."
        action={<Link href="/quality/gates" className="text-[13px] font-medium text-[var(--color-brand)] hover:underline">View governance</Link>}
      />
      <div className="panel mt-3 overflow-hidden">
        {unavailable.length ? (
          <div className="border-b border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-4 py-2.5 text-[12px] text-[var(--color-warning)]">
            Some signals are unavailable: {unavailable.join(", ")}.
          </div>
        ) : null}
        {loading && !items.length ? (
          <div className="space-y-2 p-4" aria-label="Loading attention signals">
            {[0, 1, 2].map((item) => <div key={item} className="h-12 animate-pulse rounded-lg bg-[var(--color-surface-subtle)]" />)}
          </div>
        ) : items.length ? (
          <div className="divide-y divide-[var(--color-border)]">
            {items.map((item) => {
              const Icon = iconByKind[item.kind];
              return (
                <Link
                  key={`${item.kind}:${item.id}`}
                  href={item.href}
                  className="group flex min-h-[68px] items-center gap-3 px-4 py-3 transition hover:bg-[var(--color-surface-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand)]"
                >
                  <span className={item.kind === "approval" ? "text-[var(--color-warning)]" : "text-[var(--color-danger)]"}>
                    <Icon size={17} aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold text-[var(--color-text)]">{item.title}</span>
                    <span className="mt-0.5 block truncate text-[12px] text-[var(--color-text-muted)]">{item.description}</span>
                  </span>
                  <span className="hidden shrink-0 text-[12px] text-[var(--color-text-muted)] sm:block">{relativeTime(item.timestamp)}</span>
                  <ArrowRight size={15} className="shrink-0 text-[var(--color-text-muted)] transition group-hover:translate-x-0.5 group-hover:text-[var(--color-brand)]" aria-hidden="true" />
                </Link>
              );
            })}
          </div>
        ) : (
          <div className="px-5 py-8 text-center">
            <p className="text-[14px] font-medium text-[var(--color-text)]">No immediate attention required</p>
            <p className="mt-1 text-[12px] text-[var(--color-text-muted)]">No failed blocking gates, requested approvals, or failed operations were found in the current slices.</p>
          </div>
        )}
      </div>
    </section>
  );
}
