import type { ReactNode } from "react";

export function SectionHeader({
  title,
  description,
  action,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex min-h-10 items-start justify-between gap-4">
      <div className="min-w-0">
        <h2 className="text-[16px] font-semibold leading-6 tracking-[-0.01em] text-[var(--color-text)]">{title}</h2>
        {description ? <p className="mt-1 text-[13px] leading-5 text-[var(--color-text-muted)]">{description}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
