"use client";

import { useEffect, useMemo, useState } from "react";
import { Empty, Input, Modal } from "antd";
import { ArrowRight, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { paletteDestinations } from "./portal-navigation";

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onOpenChange]);


  const destinations = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return paletteDestinations;
    return paletteDestinations.filter((item) =>
      [item.label, item.description, ...item.keywords].some((value) => value.toLowerCase().includes(term)),
    );
  }, [query]);

  const navigate = (path: string) => {
    onOpenChange(false);
    router.push(path);
  };

  return (
    <Modal
      open={open}
      footer={null}
      onCancel={() => onOpenChange(false)}
      title="Search ResearchOps"
      width={560}
      destroyOnHidden
      afterOpenChange={(visible) => { if (!visible) setQuery(""); }}
    >
      <Input
        autoFocus
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onPressEnter={() => destinations[0] && navigate(destinations[0].path)}
        prefix={<Search size={15} />}
        placeholder="Search workspaces and tools…"
        allowClear
      />

      <div className="mt-3 max-h-[430px] overflow-y-auto">
        {destinations.length ? (
          <div className="grid gap-1">
            {destinations.map((item) => (
              <button
                type="button"
                key={item.path}
                onClick={() => navigate(item.path)}
                className="group flex w-full items-center gap-3 rounded-[var(--radius-sm)] px-3 py-2.5 text-left transition hover:bg-[var(--color-surface-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]"
              >
                <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-[var(--color-surface-subtle)] text-[var(--color-text-secondary)] group-hover:text-[var(--color-brand)]">
                  {item.icon}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-medium text-[var(--color-text)]">{item.label}</span>
                  <span className="block truncate text-[12px] text-[var(--color-text-muted)]">{item.description}</span>
                </span>
                <ArrowRight size={15} className="text-[var(--color-text-muted)] opacity-0 transition group-hover:opacity-100" />
              </button>
            ))}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No matching workspace" className="my-8" />
        )}
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-[var(--color-border)] pt-3 text-[11px] text-[var(--color-text-muted)]">
        <span>Navigation search only — backend global search is not fabricated.</span>
        <span className="font-mono">↵ open · esc close</span>
      </div>
    </Modal>
  );
}
