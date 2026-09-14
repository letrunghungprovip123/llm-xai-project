import type { ReactNode } from "react";

export function PageTitle({
  title,
  description,
  eyebrow,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  eyebrow?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        {eyebrow ? (
          <p className="mb-2 text-[12px] font-medium text-[var(--color-brand)]">{eyebrow}</p>
        ) : null}
        <h1 className="text-[28px] font-semibold leading-9 tracking-[-0.035em] text-[var(--color-text)] sm:text-[30px]">
          {title}
        </h1>
        {description ? (
          <div className="mt-2 max-w-3xl text-[14px] leading-6 text-[var(--color-text-muted)]">
            {description}
          </div>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
