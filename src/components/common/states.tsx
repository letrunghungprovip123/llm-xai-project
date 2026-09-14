"use client";

import { Alert, Button, Empty, Result, Skeleton } from "antd";
import { RefreshCw } from "lucide-react";
import { ResearchOpsApiError } from "@/lib/api/client";

export function PanelSkeleton({ rows = 5 }: { rows?: number }) {
  return <div className="panel"><Skeleton active paragraph={{ rows }} /></div>;
}

export function EmptyPanel({ description = "No records match the current view." }: { description?: string }) {
  return <div className="panel py-10"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description} /></div>;
}

export function QueryError({ error, onRetry, title = "Unable to load ResearchOps data" }: { error: unknown; onRetry?: () => void; title?: string }) {
  const api = error instanceof ResearchOpsApiError ? error : null;
  return (
    <Result
      status={api?.status === 403 ? "403" : api?.status === 404 ? "404" : api?.status === 503 ? "warning" : "error"}
      title={title}
      subTitle={api ? `${api.code}: ${api.message} · request ${api.requestId}` : error instanceof Error ? error.message : "Unknown error"}
      extra={onRetry ? <Button icon={<RefreshCw size={15} />} onClick={onRetry}>Retry</Button> : undefined}
    />
  );
}

export function DegradedAlert({ message }: { message: string }) {
  return <Alert type="warning" showIcon message={message} />;
}
