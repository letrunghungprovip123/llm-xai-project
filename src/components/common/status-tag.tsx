"use client";

import { Tag } from "antd";
import { getStatusMeta, type StatusTone } from "@/lib/status/status-registry";

const toneColor: Record<StatusTone, "success" | "error" | "warning" | "processing" | "default"> = {
  success: "success",
  danger: "error",
  warning: "warning",
  info: "processing",
  neutral: "default",
};

export function StatusTag({ value }: { value?: string | null }) {
  const meta = getStatusMeta(value);
  return (
    <Tag color={toneColor[meta.tone]} className="m-0! text-[12px]! font-medium!">
      {meta.label}
    </Tag>
  );
}
