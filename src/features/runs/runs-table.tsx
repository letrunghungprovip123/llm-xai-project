import Link from "next/link";
import { Empty, Table, type TableColumnsType } from "antd";
import { ArrowRight } from "lucide-react";
import { ResourceId } from "@/components/common/resource-id";
import { StatusTag } from "@/components/common/status-tag";
import type { RunSummary } from "@/lib/api/contracts";
import { dateTime, duration } from "@/lib/format";

const columns: TableColumnsType<RunSummary> = [
  {
    title: "Status",
    dataIndex: "status",
    width: 130,
    render: (value: string) => <StatusTag value={value} />,
  },
  {
    title: "Run / flow",
    dataIndex: "flow_id",
    render: (value: string, run) => (
      <div className="min-w-0 py-1">
        <Link href={`/runs/${encodeURIComponent(run.id)}`} className="inline-flex items-center gap-1.5 font-semibold text-[var(--color-text)] hover:text-[var(--color-brand)]">
          <span className="truncate">{value}</span>
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
        <div className="mt-1"><ResourceId value={run.id} max={30} /></div>
        <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">{run.trigger_type} · {run.requested_by}</p>
      </div>
    ),
  },
  {
    title: "Started",
    dataIndex: "started_at",
    width: 210,
    responsive: ["md"],
    render: (value: string | null, run) => (
      <div>
        <div className="text-[13px] text-[var(--color-text-secondary)]">{dateTime(value || run.created_at)}</div>
        {!value ? <div className="mt-1 text-[11px] text-[var(--color-text-muted)]">Not started</div> : null}
      </div>
    ),
  },
  {
    title: "Duration",
    width: 120,
    responsive: ["sm"],
    render: (_value, run) => <span className="text-[13px] text-[var(--color-text-secondary)]">{duration(run.started_at, run.ended_at)}</span>,
  },
];

export function RunsTable({ runs, loading, hasFilters, onClearFilters }: { runs: RunSummary[]; loading: boolean; hasFilters: boolean; onClearFilters: () => void }) {
  return (
    <Table<RunSummary>
      rowKey="id"
      loading={loading}
      pagination={false}
      dataSource={runs}
      columns={columns}
      locale={{
        emptyText: (
          <div className="py-10">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={hasFilters ? "No runs match these filters." : "No pipeline runs are registered yet."}
            >
              {hasFilters ? <button type="button" onClick={onClearFilters} className="text-[13px] font-medium text-[var(--color-brand)] hover:underline">Clear filters</button> : null}
            </Empty>
          </div>
        ),
      }}
    />
  );
}
