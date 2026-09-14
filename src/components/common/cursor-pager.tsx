"use client";

import { Button } from "antd";
import { ChevronLeft, ChevronRight } from "lucide-react";

export function CursorPager({ hasMore, canBack, onNext, onBack, loading, limit }: { hasMore: boolean; canBack: boolean; onNext: () => void; onBack: () => void; loading?: boolean; limit: number }) {
  return <div className="flex items-center justify-between gap-3 border-t border-[var(--panel-border)] px-4 py-3"><Button icon={<ChevronLeft size={14} />} disabled={!canBack || loading} onClick={onBack}>Previous</Button><span className="text-xs text-[var(--muted)]">Up to {limit} records · cursor pagination</span><Button icon={<ChevronRight size={14} />} iconPosition="end" disabled={!hasMore || loading} onClick={onNext}>Next</Button></div>;
}
