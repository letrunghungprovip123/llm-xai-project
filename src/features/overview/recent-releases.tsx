import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { StatusTag } from "@/components/common/status-tag";
import { SectionHeader } from "@/components/ui/section-header";
import type { ReleaseSummary } from "@/lib/api/contracts";
import { relativeTime } from "@/lib/format";

export function RecentReleases({ releases, loading, unavailable }: { releases: ReleaseSummary[]; loading?: boolean; unavailable?: boolean }) {
  return (
    <section>
      <SectionHeader
        title="Recent delivery"
        description="Latest research release records and lifecycle state."
        action={<Link href="/delivery/releases" className="text-[13px] font-medium text-[var(--color-brand)] hover:underline">View releases</Link>}
      />
      <div className="panel mt-3 overflow-hidden">
        {unavailable ? (
          <div className="px-5 py-8 text-center text-[13px] text-[var(--color-warning)]">Release data is temporarily unavailable.</div>
        ) : loading && !releases.length ? (
          <div className="space-y-3 p-4" aria-label="Loading releases">
            {[0, 1, 2].map((item) => <div key={item} className="h-12 animate-pulse rounded-lg bg-[var(--color-surface-subtle)]" />)}
          </div>
        ) : releases.length ? (
          <div className="divide-y divide-[var(--color-border)]">
            {releases.map((release) => (
              <Link
                key={release.id}
                href={`/delivery/releases/${encodeURIComponent(release.id)}`}
                className="group flex min-h-[68px] items-center gap-3 px-4 py-3 transition hover:bg-[var(--color-surface-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-brand)]"
              >
                <StatusTag value={release.status} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-semibold text-[var(--color-text)]">{release.id}</span>
                  <span className="mt-0.5 block truncate text-[11px] text-[var(--color-text-muted)]">{release.release_type}</span>
                </span>
                <span className="hidden shrink-0 text-[12px] text-[var(--color-text-muted)] sm:block">{relativeTime(release.promoted_at || release.created_at)}</span>
                <ArrowRight size={15} className="text-[var(--color-text-muted)] transition group-hover:translate-x-0.5 group-hover:text-[var(--color-brand)]" aria-hidden="true" />
              </Link>
            ))}
          </div>
        ) : (
          <div className="px-5 py-8 text-center text-[13px] text-[var(--color-text-muted)]">No release records are available.</div>
        )}
      </div>
    </section>
  );
}
