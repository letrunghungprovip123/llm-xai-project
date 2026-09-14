"use client";

import { useState } from "react";
import { Button, Drawer, Input, Select, Tag } from "antd";
import { Filter, Search, X } from "lucide-react";
import type { RegistryItem } from "@/lib/api/contracts";
import type { UrlFilterState, UrlFilterUpdate } from "@/components/common/use-url-filters";

const runStatuses = ["PENDING", "WAITING_APPROVAL", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"];

export function RunsFilters({
  value,
  onChange,
  flows,
}: {
  value: UrlFilterState;
  onChange: (next: UrlFilterUpdate) => void;
  flows: RegistryItem[];
}) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [requester, setRequester] = useState(value.requested_by || "");
  const [commit, setCommit] = useState(value.source_commit || "");

  const update = (patch: UrlFilterUpdate) => onChange({ ...value, ...patch });
  const activeEntries = Object.entries(value).filter(([, current]) => current);

  return (
    <>
      <section className="flex flex-col gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3 sm:flex-row sm:flex-wrap sm:items-center">
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          value={value.flow_id || undefined}
          onChange={(flowId) => update({ flow_id: flowId })}
          placeholder="Flow"
          suffixIcon={<Search size={14} />}
          className="w-full sm:w-[260px]"
          options={flows.map((flow) => ({ value: flow.id, label: flow.title ? `${flow.id} — ${flow.title}` : flow.id }))}
        />
        <Select
          allowClear
          value={value.status || undefined}
          onChange={(status) => update({ status })}
          placeholder="Status"
          className="w-full sm:w-[190px]"
          options={runStatuses.map((status) => ({ value: status, label: status.replaceAll("_", " ").toLowerCase().replace(/^./, (char) => char.toUpperCase()) }))}
        />
        <Button icon={<Filter size={14} />} onClick={() => { setRequester(value.requested_by || ""); setCommit(value.source_commit || ""); setAdvancedOpen(true); }}>More filters</Button>
        {activeEntries.length ? (
          <Button type="text" icon={<X size={14} />} onClick={() => onChange({})}>Clear</Button>
        ) : null}
      </section>

      {activeEntries.length ? (
        <div className="flex flex-wrap gap-2" aria-label="Active filters">
          {activeEntries.map(([key, current]) => (
            <Tag key={key} closable onClose={(event) => { event.preventDefault(); update({ [key]: undefined }); }} className="m-0!">
              {filterLabel(key)}: {current}
            </Tag>
          ))}
        </div>
      ) : null}

      <Drawer title="More run filters" open={advancedOpen} onClose={() => setAdvancedOpen(false)} width={380}>
        <div className="space-y-5">
          <label className="block">
            <span className="mb-2 block text-[13px] font-medium text-[var(--color-text-secondary)]">Requested by</span>
            <Input value={requester} onChange={(event) => setRequester(event.target.value)} placeholder="Exact requester" allowClear />
          </label>
          <label className="block">
            <span className="mb-2 block text-[13px] font-medium text-[var(--color-text-secondary)]">Source commit</span>
            <Input value={commit} onChange={(event) => setCommit(event.target.value)} placeholder="Exact source commit" allowClear className="font-mono" />
          </label>
          <p className="text-[12px] leading-5 text-[var(--color-text-muted)]">These filters use exact control-plane fields; no client-side full-dataset search is fabricated.</p>
          <div className="flex justify-end gap-2">
            <Button onClick={() => { setRequester(""); setCommit(""); update({ requested_by: undefined, source_commit: undefined }); }}>Clear advanced</Button>
            <Button type="primary" onClick={() => { update({ requested_by: requester.trim() || undefined, source_commit: commit.trim() || undefined }); setAdvancedOpen(false); }}>Apply</Button>
          </div>
        </div>
      </Drawer>
    </>
  );
}

function filterLabel(key: string) {
  if (key === "flow_id") return "Flow";
  if (key === "requested_by") return "Requester";
  if (key === "source_commit") return "Commit";
  return "Status";
}
