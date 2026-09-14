"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Alert, App, Button } from "antd";
import { Ban, RotateCcw } from "lucide-react";
import { JsonView } from "@/components/common/json-view";
import { ReasonCommandModal } from "@/components/common/command-modal";
import { PanelSkeleton, QueryError } from "@/components/common/states";
import { ResourceId } from "@/components/common/resource-id";
import { StatusTag } from "@/components/common/status-tag";
import { PageTitle } from "@/components/ui/page-title";
import { SectionHeader } from "@/components/ui/section-header";
import { TechnicalDetails } from "@/components/ui/technical-details";
import { RunActivity } from "@/features/runs/run-activity";
import { RunOutputs } from "@/features/runs/run-outputs";
import { StageTimeline } from "@/features/runs/stage-timeline";
import type { RunCancelRequest, RunRetryRequest } from "@/lib/api/contracts";
import { dateTime, duration, relativeTime } from "@/lib/format";
import { isLiveRunStatus } from "@/lib/status/status-registry";
import { useCapabilities, useResearchOpsMutations, useRun, useRunEvents, useRunOutputs, useRunReceipt, useRunStages } from "@/lib/query/researchops-hooks";

const isRunCancelStatus = (value: string): value is RunCancelRequest["expected_status"] => value === "PENDING" || value === "WAITING_APPROVAL" || value === "RUNNING";
const isRunRetryStatus = (value: string): value is RunRetryRequest["expected_status"] => value === "FAILED" || value === "CANCELLED";

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const id = decodeURIComponent(runId);
  const router = useRouter();
  const { message } = App.useApp();
  const run = useRun(id);
  const live = isLiveRunStatus(run.data?.status);
  const stages = useRunStages(id, live);
  const events = useRunEvents(id, live);
  const outputs = useRunOutputs(id, live);
  const receipt = useRunReceipt(id);
  const capabilities = useCapabilities();
  const mutations = useResearchOpsMutations();
  const [command, setCommand] = useState<"cancel" | "retry" | null>(null);

  if (run.isLoading) return <PanelSkeleton rows={10} />;
  if (run.isError || !run.data) return <QueryError error={run.error} title="Unable to load this run" />;

  const current = run.data;
  const canCancel = isRunCancelStatus(current.status);
  const canRetry = isRunRetryStatus(current.status);
  const mutationsEnabled = capabilities.data?.mutation_api_enabled !== false;

  const execute = async (reason: string, key: string) => {
    try {
      if (command === "cancel") {
        if (!isRunCancelStatus(current.status)) {
          message.error("Run is no longer cancellable. Refresh and try again.");
          return;
        }
        const result = await mutations.cancelRun.mutateAsync({ id, body: { reason, expected_status: current.status }, key });
        message.success("Cancel requested. The control operation is processing.");
        setCommand(null);
        router.push(`/operations/${result.operation_id}`);
        return;
      }
      if (command === "retry") {
        if (!isRunRetryStatus(current.status)) {
          message.error("Run is no longer retryable. Refresh and try again.");
          return;
        }
        const result = await mutations.retryRun.mutateAsync({ id, body: { reason, expected_status: current.status, parameters: current.parameters, input_artifact_ids: {} }, key });
        message.success("Retry requested. The control operation is processing.");
        setCommand(null);
        router.push(`/operations/${result.operation_id}`);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Command failed");
    }
  };

  const actions = (
    <>
      {canCancel ? <Button danger icon={<Ban size={14} />} disabled={!mutationsEnabled} onClick={() => setCommand("cancel")}>Cancel run</Button> : null}
      {canRetry ? <Button icon={<RotateCcw size={14} />} disabled={!mutationsEnabled} onClick={() => setCommand("retry")}>Retry run</Button> : null}
    </>
  );

  return (
    <div className="space-y-7">
      <PageTitle
        eyebrow="Runs"
        title={<span className="inline-flex flex-wrap items-center gap-3"><span>{current.flow_id}</span><StatusTag value={current.status} /></span>}
        description={<span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1"><ResourceId value={current.id} /><span>Started {relativeTime(current.started_at)}</span><span>·</span><span>{duration(current.started_at, current.ended_at)}</span></span>}
        actions={actions}
      />

      {current.error_summary ? <Alert type="error" showIcon message="Run failure" description={current.error_summary} /> : null}

      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-8">
          <section>
            <SectionHeader title="Pipeline" description="Stage execution order is provided by the control plane; attempts are shown as recorded." />
            <div className="mt-4">
              <StageTimeline stages={stages.data || []} loading={stages.isLoading} unavailable={stages.isError} />
            </div>
          </section>

          <section>
            <SectionHeader title="Outputs" description={`${outputs.data?.length || 0} registered artifact output${outputs.data?.length === 1 ? "" : "s"}.`} />
            <div className="mt-3"><RunOutputs outputs={outputs.data || []} loading={outputs.isLoading} unavailable={outputs.isError} /></div>
          </section>

          <section>
            <SectionHeader title="Latest activity" description="Newest control-plane events for this pipeline run." />
            <div className="mt-3"><RunActivity events={events.data || []} loading={events.isLoading} unavailable={events.isError} /></div>
          </section>

          <TechnicalDetails>
            <div className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-2">
                <TechnicalValue label="Source commit"><ResourceId value={current.source_commit} /></TechnicalValue>
                <TechnicalValue label="Registry SHA"><ResourceId value={current.registry_sha256} /></TechnicalValue>
                <TechnicalValue label="Environment"><ResourceId value={current.environment_snapshot_id} /></TechnicalValue>
                <TechnicalValue label="Idempotency key"><ResourceId value={current.idempotency_key} /></TechnicalValue>
              </div>
              <div className="grid gap-5 xl:grid-cols-2">
                <section><h3 className="mb-2 text-[13px] font-semibold">Parameters</h3><JsonView value={current.parameters} /></section>
                <section><h3 className="mb-2 text-[13px] font-semibold">Prefect metadata</h3><JsonView value={current.prefect} /></section>
              </div>
              <section>
                <h3 className="mb-2 text-[13px] font-semibold">Immutable run receipt</h3>
                {receipt.isError ? <p className="text-[12px] text-[var(--color-warning)]">Receipt data is temporarily unavailable.</p> : receipt.data ? <JsonView value={receipt.data} /> : <p className="text-[12px] text-[var(--color-text-muted)]">No immutable run receipt is registered.</p>}
              </section>
            </div>
          </TechnicalDetails>
        </div>

        <aside className="self-start rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 xl:sticky xl:top-[calc(var(--shell-header-height)+32px)]">
          <h2 className="text-[14px] font-semibold text-[var(--color-text)]">Run details</h2>
          <dl className="mt-4 divide-y divide-[var(--color-border)]">
            <DetailRow label="Status"><StatusTag value={current.status} /></DetailRow>
            <DetailRow label="Requested by">{current.requested_by}</DetailRow>
            <DetailRow label="Trigger">{current.trigger_type}</DetailRow>
            <DetailRow label="Created">{dateTime(current.created_at)}</DetailRow>
            <DetailRow label="Started">{dateTime(current.started_at)}</DetailRow>
            <DetailRow label="Ended">{dateTime(current.ended_at)}</DetailRow>
            <DetailRow label="Duration">{duration(current.started_at, current.ended_at)}</DetailRow>
          </dl>

          {Object.keys(current.stage_counts).length ? (
            <div className="mt-5 border-t border-[var(--color-border)] pt-4">
              <h3 className="text-[12px] font-medium text-[var(--color-text-secondary)]">Stage summary</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {Object.entries(current.stage_counts).map(([status, count]) => <span key={status} className="inline-flex items-center gap-1.5"><StatusTag value={status} /><span className="text-[12px] text-[var(--color-text-muted)]">{count}</span></span>)}
              </div>
            </div>
          ) : null}
        </aside>
      </div>

      <ReasonCommandModal
        open={Boolean(command)}
        title={command === "cancel" ? "Cancel run" : "Retry run"}
        confirmText={command === "cancel" ? "Request cancellation" : "Request retry"}
        danger={command === "cancel"}
        loading={mutations.cancelRun.isPending || mutations.retryRun.isPending}
        onCancel={() => setCommand(null)}
        onSubmit={execute}
      />
    </div>
  );
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="grid grid-cols-[104px_minmax(0,1fr)] gap-3 py-3 text-[12px]"><dt className="text-[var(--color-text-muted)]">{label}</dt><dd className="min-w-0 text-right text-[var(--color-text-secondary)]">{children || "—"}</dd></div>;
}

function TechnicalValue({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="rounded-[var(--radius-md)] bg-[var(--color-surface-subtle)] p-3"><div className="text-[11px] font-medium text-[var(--color-text-muted)]">{label}</div><div className="mt-1 min-w-0 text-[13px]">{children}</div></div>;
}
