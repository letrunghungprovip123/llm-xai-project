import type { ReactNode } from "react";

export function KvGrid({ items }: { items: Array<[ReactNode, ReactNode]> }) {
  return <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 xl:grid-cols-3">{items.map(([label, value], i) => <div key={i} className="min-w-0"><dt className="text-[11px] font-semibold uppercase tracking-[.12em] text-[var(--muted)]">{label}</dt><dd className="mt-1 min-w-0 text-sm">{value ?? "—"}</dd></div>)}</dl>;
}
