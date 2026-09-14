import type { ReactNode } from "react";

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="text-[11px] font-semibold uppercase tracking-[.16em] text-[var(--brand)]">{eyebrow}</p>}
        <h1 className="mt-1 text-2xl font-semibold tracking-[-.03em] sm:text-3xl">{title}</h1>
        {description && <div className="mt-2 max-w-4xl text-sm leading-6 text-[var(--muted)]">{description}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
