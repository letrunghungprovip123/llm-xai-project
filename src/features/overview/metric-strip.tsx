import Link from "next/link";
import type { ReactNode } from "react";

export type MetricItem = {
  label: string;
  value: string;
  hint: string;
  href: string;
  icon: ReactNode;
};

export function MetricStrip({ items }: { items: MetricItem[] }) {
  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Operational summary">
      {items.map((item) => (
        <Link
          key={item.label}
          href={item.href}
          className="panel group flex min-h-[132px] flex-col justify-between p-4 transition hover:border-[var(--color-border-strong)] hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]"
        >
          <div className="flex items-center justify-between gap-3 text-[13px] font-medium text-[var(--color-text-secondary)]">
            <span>{item.label}</span>
            <span className="text-[var(--color-text-muted)] transition group-hover:text-[var(--color-brand)]">{item.icon}</span>
          </div>
          <div>
            <div className="text-[28px] font-semibold leading-9 tracking-[-0.04em] text-[var(--color-text)]">{item.value}</div>
            <p className="mt-1 text-[12px] leading-5 text-[var(--color-text-muted)]">{item.hint}</p>
          </div>
        </Link>
      ))}
    </section>
  );
}
