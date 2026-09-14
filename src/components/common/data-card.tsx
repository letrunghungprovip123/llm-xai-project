import type { ReactNode } from "react";
export function DataCard({ title, extra, children, className = "" }: { title?: ReactNode; extra?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel overflow-hidden ${className}`}><div className="flex min-h-12 items-center justify-between gap-3 border-b border-[var(--panel-border)] px-4 py-3">{title && <h2 className="text-sm font-semibold">{title}</h2>}{extra}</div><div>{children}</div></section>;
}
