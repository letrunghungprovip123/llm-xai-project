"use client";

import { Button } from "antd";
import { Activity, PackageCheck, RefreshCw, ShieldAlert, UserCheck } from "lucide-react";
import { PageTitle } from "@/components/ui/page-title";
import { ActiveRuns } from "@/features/overview/active-runs";
import { AttentionQueue, type AttentionItem } from "@/features/overview/attention-queue";
import { MetricStrip, type MetricItem } from "@/features/overview/metric-strip";
import { RecentReleases } from "@/features/overview/recent-releases";
import type { CursorPage } from "@/lib/api/contracts";
import { useApprovals, useGates, useOperations, useReleases, useRuns } from "@/lib/query/researchops-hooks";

function countLabel<T>(data: CursorPage<T> | undefined, loading: boolean, failed: boolean) {
  if (failed && !data) return "—";
  if (!data && loading) return "…";
  if (!data) return "0";
  return data.page.has_more ? `${data.items.length}+` : String(data.items.length);
}

function timestampValue(value: string | null) {
  if (!value) return 0;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

export default function MissionControlPage() {
  const runs = useRuns({ limit: 5, status: "RUNNING" });
  const gates = useGates({ limit: 5, effective_status: "FAILED", blocking: true });
  const approvals = useApprovals({ limit: 5, status: "REQUESTED" });
  const failedOperations = useOperations({ limit: 5, status: "FAILED" });
  const partialOperations = useOperations({ limit: 5, status: "FAILED_PARTIAL" });
  const candidateReleases = useReleases({ limit: 5, status: "CANDIDATE" });
  const releases = useReleases({ limit: 5 });

  const refresh = () => {
    void Promise.all([
      runs.refetch(),
      gates.refetch(),
      approvals.refetch(),
      failedOperations.refetch(),
      partialOperations.refetch(),
      candidateReleases.refetch(),
      releases.refetch(),
    ]);
  };

  const metrics: MetricItem[] = [
    {
      label: "Active runs",
      value: countLabel(runs.data, runs.isLoading, runs.isError),
      hint: "Running pipeline executions",
      href: "/runs?status=RUNNING",
      icon: <Activity size={17} />,
    },
    {
      label: "Blocking issues",
      value: countLabel(gates.data, gates.isLoading, gates.isError),
      hint: "Failed blocking gates",
      href: "/quality/gates?effective_status=FAILED&blocking=true",
      icon: <ShieldAlert size={17} />,
    },
    {
      label: "Need approval",
      value: countLabel(approvals.data, approvals.isLoading, approvals.isError),
      hint: "Requested governance decisions",
      href: "/quality/approvals?status=REQUESTED",
      icon: <UserCheck size={17} />,
    },
    {
      label: "Candidate releases",
      value: countLabel(candidateReleases.data, candidateReleases.isLoading, candidateReleases.isError),
      hint: "Release candidates awaiting progression",
      href: "/delivery/releases?status=CANDIDATE",
      icon: <PackageCheck size={17} />,
    },
  ];

  const attention: Array<AttentionItem & { priority: number }> = [
    ...(gates.data?.items || []).map((gate) => ({
      id: gate.id,
      kind: "gate" as const,
      priority: 0,
      title: gate.gate_id,
      description: `${gate.scope_type} · ${gate.scope_id} · blocking ${gate.severity.toLowerCase()}`,
      timestamp: gate.updated_at,
      href: `/quality/gates/${encodeURIComponent(gate.id)}`,
    })),
    ...(failedOperations.data?.items || []).map((operation) => ({
      id: operation.id,
      kind: "operation" as const,
      priority: 1,
      title: operation.operation_type,
      description: `${operation.target_type} · ${operation.target_id} · failed`,
      timestamp: operation.updated_at,
      href: `/operations/${encodeURIComponent(operation.id)}`,
    })),
    ...(partialOperations.data?.items || []).map((operation) => ({
      id: operation.id,
      kind: "operation" as const,
      priority: 1,
      title: operation.operation_type,
      description: `${operation.target_type} · ${operation.target_id} · partially failed`,
      timestamp: operation.updated_at,
      href: `/operations/${encodeURIComponent(operation.id)}`,
    })),
    ...(approvals.data?.items || []).map((approval) => ({
      id: approval.id,
      kind: "approval" as const,
      priority: 2,
      title: `Approval · ${approval.target_type}`,
      description: `${approval.target_id} · ${approval.policy}`,
      timestamp: approval.requested_at,
      href: `/quality/approvals/${encodeURIComponent(approval.id)}`,
    })),
  ].sort((left, right) => left.priority - right.priority || timestampValue(right.timestamp) - timestampValue(left.timestamp));

  const unavailable = [
    gates.isError ? "gates" : null,
    failedOperations.isError || partialOperations.isError ? "operations" : null,
    approvals.isError ? "approvals" : null,
  ].filter((value): value is string => Boolean(value));

  return (
    <div className="space-y-8">
      <PageTitle
        eyebrow="Mission Control"
        title="Overview"
        description="Research operations at a glance: active executions, governance blockers, decisions waiting on people, and recent delivery."
        actions={<Button icon={<RefreshCw size={14} />} loading={[runs, gates, approvals, failedOperations, partialOperations, candidateReleases, releases].some((query) => query.isFetching)} onClick={refresh}>Refresh</Button>}
      />

      <MetricStrip items={metrics} />

      <AttentionQueue items={attention.slice(0, 8)} unavailable={unavailable} loading={[gates, failedOperations, partialOperations, approvals].some((query) => query.isLoading)} />

      <div className="grid gap-8 xl:grid-cols-2">
        <ActiveRuns runs={runs.data?.items || []} loading={runs.isLoading} unavailable={runs.isError} />
        <RecentReleases releases={releases.data?.items || []} loading={releases.isLoading} unavailable={releases.isError} />
      </div>
    </div>
  );
}
