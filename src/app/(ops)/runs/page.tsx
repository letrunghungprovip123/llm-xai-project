"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { App, Button, Form, Input, Modal, Select } from "antd";
import { Plus } from "lucide-react";
import { CursorPager } from "@/components/common/cursor-pager";
import { QueryError } from "@/components/common/states";
import { useCursorPager } from "@/components/common/use-cursor";
import { useUrlFilters } from "@/components/common/use-url-filters";
import { PageTitle } from "@/components/ui/page-title";
import { RunsFilters } from "@/features/runs/runs-filters";
import { RunsTable } from "@/features/runs/runs-table";
import { newCommandId } from "@/lib/api/client";
import type { JsonObject } from "@/lib/api/contracts";
import { useCapabilities, useFlows, useResearchOpsMutations, useRuns } from "@/lib/query/researchops-hooks";

function isFormValidationError(error: unknown) {
  return typeof error === "object" && error !== null && "errorFields" in error;
}

function parseObject(raw?: string): JsonObject {
  if (!raw?.trim()) return {};
  const parsed: unknown = JSON.parse(raw);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) throw new SyntaxError("Expected a JSON object");
  return parsed as JsonObject;
}

function parseArtifactMap(raw?: string): Record<string, string> {
  const parsed = parseObject(raw);
  if (Object.values(parsed).some((value) => typeof value !== "string")) throw new SyntaxError("Artifact IDs must be string values");
  return parsed as Record<string, string>;
}

export default function RunsPage() {
  const router = useRouter();
  const { message } = App.useApp();
  const [filters, setFilters] = useUrlFilters(["flow_id", "status", "requested_by", "source_commit"]);
  const resetKey = JSON.stringify(filters);
  const pager = useCursorPager(resetKey);
  const runs = useRuns({ limit: 50, cursor: pager.cursor, ...filters });
  const flows = useFlows();
  const capabilities = useCapabilities();
  const mutations = useResearchOpsMutations();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const [commandId, setCommandId] = useState(newCommandId());

  const submit = async () => {
    try {
      const values = await form.validateFields();
      const result = await mutations.triggerRun.mutateAsync({
        key: commandId,
        body: {
          flow_id: values.flow_id,
          reason: values.reason,
          input_artifact_ids: parseArtifactMap(values.input_artifact_ids),
          parameters: parseObject(values.parameters),
        },
      });
      message.success("Run command accepted. The control operation is processing.");
      setOpen(false);
      router.push(`/operations/${result.operation_id}`);
    } catch (error) {
      if (error instanceof SyntaxError) message.error(error.message);
      else if (error instanceof Error && !isFormValidationError(error)) message.error(error.message);
    }
  };

  const openTrigger = () => {
    setCommandId(newCommandId());
    form.resetFields();
    setOpen(true);
  };

  return (
    <div className="space-y-6">
      <PageTitle
        eyebrow="Work"
        title="Runs"
        description="Track pipeline execution lifecycle and enter a run to inspect stages, outputs, activity, and reproducibility metadata."
        actions={<Button type="primary" icon={<Plus size={14} />} disabled={capabilities.data?.mutation_api_enabled === false} onClick={openTrigger}>New run</Button>}
      />

      <RunsFilters value={filters} onChange={setFilters} flows={flows.data || []} />

      {runs.isError ? (
        <QueryError error={runs.error} onRetry={() => { void runs.refetch(); }} title="Unable to load pipeline runs" />
      ) : (
        <section className="panel overflow-hidden">
          <RunsTable runs={runs.data?.items || []} loading={runs.isLoading} hasFilters={Object.keys(filters).length > 0} onClearFilters={() => setFilters({})} />
          <CursorPager
            limit={runs.data?.page.limit || 50}
            hasMore={Boolean(runs.data?.page.has_more)}
            canBack={pager.canBack}
            loading={runs.isFetching}
            onBack={pager.back}
            onNext={() => pager.next(runs.data?.page.next_cursor)}
          />
        </section>
      )}

      <Modal open={open} title="Trigger official flow" okText="Submit run" confirmLoading={mutations.triggerRun.isPending} onCancel={() => setOpen(false)} onOk={submit} destroyOnHidden>
        <p className="mb-4 text-[13px] leading-5 text-[var(--color-text-muted)]">Command ID <code>{commandId}</code>. FastAPI remains the final RBAC and execution authority.</p>
        <Form form={form} layout="vertical">
          <Form.Item name="flow_id" label="Flow" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" options={(flows.data || []).map((flow) => ({ value: flow.id, label: flow.title ? `${flow.id} — ${flow.title}` : flow.id }))} />
          </Form.Item>
          <Form.Item name="reason" label="Reason" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="input_artifact_ids" label="Input artifact IDs (JSON object)"><Input.TextArea rows={3} placeholder='{"dataset": "artifact_id"}' className="font-mono" /></Form.Item>
          <Form.Item name="parameters" label="Parameters (JSON object)"><Input.TextArea rows={4} placeholder="{}" className="font-mono" /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
