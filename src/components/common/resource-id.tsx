"use client";

import { App, Button, Tooltip } from "antd";
import { Copy } from "lucide-react";

export function ResourceId({ value, max = 34 }: { value?: string | null; max?: number }) {
  const { message } = App.useApp();
  if (!value) return <span className="text-[var(--muted)]">—</span>;
  const compact = value.length > max ? `${value.slice(0, Math.ceil(max * .58))}…${value.slice(-Math.floor(max * .28))}` : value;
  return (
    <span className="inline-flex min-w-0 items-center gap-1 font-mono text-xs">
      <Tooltip title={value}><span className="truncate">{compact}</span></Tooltip>
      <Button type="text" size="small" aria-label={`Copy ${value}`} icon={<Copy size={12} />} onClick={async (e) => { e.stopPropagation(); await navigator.clipboard.writeText(value); message.success("Copied"); }} />
    </span>
  );
}
