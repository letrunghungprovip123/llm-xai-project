import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";

export function TechnicalDetails({ children, label = "Technical details" }: { children: ReactNode; label?: string }) {
  return (
    <details className="group border-t border-[var(--color-border)] pt-4">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-[var(--radius-sm)] py-2 text-[13px] font-medium text-[var(--color-text-secondary)] outline-none transition hover:text-[var(--color-text)] focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]">
        <span>{label}</span>
        <ChevronDown size={15} className="transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div className="pt-4">{children}</div>
    </details>
  );
}
