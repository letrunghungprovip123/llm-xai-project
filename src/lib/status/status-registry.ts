export type StatusTone = "success" | "danger" | "warning" | "info" | "neutral";

export type StatusMeta = {
  label: string;
  tone: StatusTone;
};

const STATUS_REGISTRY: Record<string, StatusMeta> = {
  READY: { label: "Ready", tone: "success" },
  SUCCESS: { label: "Success", tone: "success" },
  SUCCEEDED: { label: "Succeeded", tone: "success" },
  COMPLETED: { label: "Completed", tone: "success" },
  PASSED: { label: "Passed", tone: "success" },
  PASS: { label: "Pass", tone: "success" },
  CERTIFIED: { label: "Certified", tone: "success" },
  APPROVED: { label: "Approved", tone: "success" },
  VERIFIED: { label: "Verified", tone: "success" },
  PROMOTED: { label: "Promoted", tone: "success" },
  OK: { label: "OK", tone: "success" },

  FAILED: { label: "Failed", tone: "danger" },
  FAILED_PARTIAL: { label: "Partially failed", tone: "danger" },
  FAIL: { label: "Fail", tone: "danger" },
  REJECTED: { label: "Rejected", tone: "danger" },
  BLOCKED: { label: "Blocked", tone: "danger" },
  ERROR: { label: "Error", tone: "danger" },

  RUNNING: { label: "Running", tone: "info" },
  IN_PROGRESS: { label: "In progress", tone: "info" },
  PROCESSING: { label: "Processing", tone: "info" },
  UPLOADED: { label: "Uploaded", tone: "info" },
  ACTIVE: { label: "Active", tone: "info" },
  CHAMPION: { label: "Champion", tone: "info" },

  DEGRADED: { label: "Degraded", tone: "warning" },
  WAIVED: { label: "Waived", tone: "warning" },
  READY_WITH_LIMITATIONS: { label: "Ready with limitations", tone: "warning" },
  WARNING: { label: "Warning", tone: "warning" },

  PENDING: { label: "Pending", tone: "neutral" },
  REQUESTED: { label: "Requested", tone: "neutral" },
  WAITING_APPROVAL: { label: "Waiting approval", tone: "neutral" },
  CANDIDATE: { label: "Candidate", tone: "neutral" },
  DRAFT: { label: "Draft", tone: "neutral" },
  PLANNED: { label: "Planned", tone: "neutral" },
  DISABLED: { label: "Disabled", tone: "neutral" },
  CANCELLED: { label: "Cancelled", tone: "neutral" },
  EXPIRED: { label: "Expired", tone: "neutral" },
  SUPERSEDED: { label: "Superseded", tone: "neutral" },
  REVOKED: { label: "Revoked", tone: "neutral" },
};

const LIVE_RUN_STATUSES = new Set(["PENDING", "WAITING_APPROVAL", "RUNNING"]);

const TERMINAL_OPERATION_STATUSES = new Set([
  "SUCCEEDED",
  "FAILED",
  "FAILED_PARTIAL",
  "CANCELLED",
]);

function normalizeStatus(value?: string | null): string {
  return (value || "UNKNOWN").trim().toUpperCase();
}

function humanizeStatus(value: string): string {
  if (!value) return "Unknown";
  return value
    .toLowerCase()
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function getStatusMeta(value?: string | null): StatusMeta {
  const key = normalizeStatus(value);
  return STATUS_REGISTRY[key] ?? { label: humanizeStatus(key), tone: "neutral" };
}

export function isTerminalOperationStatus(value?: string | null): boolean {
  return TERMINAL_OPERATION_STATUSES.has(normalizeStatus(value));
}

export function isLiveRunStatus(value?: string | null): boolean {
  return LIVE_RUN_STATUSES.has(normalizeStatus(value));
}
