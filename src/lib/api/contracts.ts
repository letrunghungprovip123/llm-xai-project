export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = Record<string, any>;

export type PageInfo = { limit: number; has_more: boolean; next_cursor: string | null };
export type CursorPage<T> = { items: T[]; page: PageInfo };
export type ErrorBody = { code: string; message: string; request_id: string; details: JsonObject };
export type ErrorResponse = { error: ErrorBody };

export type DependencyState = { status: "READY" | "DEGRADED" | "FAILED" | "DISABLED"; detail: string | null };
export type HealthResponse = { status: "ok"; service: string };
export type ReadinessResponse = { ready: boolean; service: string; dependencies: Record<string, DependencyState> };
export type VersionResponse = {
  service: string; api_version: string; git_commit: string; git_dirty: boolean;
  alembic_head: string | null; database_revision: string | null;
  stage_registry_sha256: string; flow_catalog_sha256: string; gate_catalog_sha256: string;
  promotion_policy_sha256: string; prefect_expected_version: string; mlflow_expected_version: string;
};
export type CapabilityResponse = {
  auth_mode: string; artifact_profile: string; prefect_enabled: boolean; mlflow_enabled: boolean; mutation_api_enabled: boolean;
};
export type RegistryItem = { id: string; version: number | null; title: string | null; description: string | null; status: string; metadata: JsonObject };

export type RunSummary = {
  id: string; flow_id: string; status: string; trigger_type: string; requested_by: string;
  source_commit: string; created_at: string; started_at: string | null; ended_at: string | null; updated_at: string;
};
export type RunDetail = RunSummary & {
  registry_sha256: string; environment_snapshot_id: string; idempotency_key: string; parameters: JsonObject;
  error_summary: string | null; stage_counts: Record<string, number>; prefect: JsonObject | null;
};
export type StageRunView = {
  id: string; pipeline_run_id: string; stage_id: string; stage_version: number; attempt: number; status: string;
  approval_policy: string; started_at: string | null; ended_at: string | null; exit_code: number | null;
  error_type: string | null; error_message: string | null;
};
export type RunEventView = { id: number; pipeline_run_id: string; stage_run_id: string | null; event_type: string; payload: JsonObject; occurred_at: string };
export type RunOutputView = { stage_run_id: string; output_name: string; artifact_id: string; artifact_type: string; manifest_sha256: string; created_at: string };
export type RunReceiptView = { pipeline_run_id: string; artifact_id: string; manifest_sha256: string; created_at: string } | null;

export type ArtifactSummary = {
  id: string; artifact_type: string; schema_version: string; status: string; manifest_sha256: string;
  producer_stage_run_id: string | null; source_commit: string; created_at: string; verified_at: string | null;
  certified_at: string | null; limitations: any[];
};
export type ArtifactDetail = ArtifactSummary & { environment_snapshot_id: string | null; metadata: JsonObject };
export type ArtifactFileView = {
  id: number; relative_path: string; sha256: string; size_bytes: number; row_count: number | null;
  column_count: number | null; media_type: string; download_available: boolean;
};
export type LineageNode = { artifact_id: string; artifact_type: string; schema_version: string; status: string; manifest_sha256: string };
export type LineageEdgeView = { parent_artifact_id: string; child_artifact_id: string; relationship_type: string };
export type LineageGraph = { root_artifact_id: string; nodes: LineageNode[]; edges: LineageEdgeView[]; truncated: boolean };

export type GateSummary = {
  id: string; gate_id: string; scope_type: string; scope_id: string; status: string; evaluation_outcome: string | null;
  effective_status: string | null; current_evaluation_id: string | null; blocking: boolean; severity: string;
  updated_at: string; waiver: JsonObject | null;
};
export type GateEvaluationView = {
  id: string; evaluation_key: string; payload_sha256: string; gate_id: string; scope_type: string; scope_id: string;
  outcome: string; blocking: boolean; severity: string; adapter_id: string; adapter_version: number; policy_id: string;
  policy_version: string; source_artifact_id: string | null; source_manifest_sha256: string | null;
  evidence_artifact_id: string | null; evidence_manifest_sha256: string | null; source_contract: string;
  expected: JsonObject; observed: JsonObject; checks: any[]; limitations: any[]; source_contracts: any[];
  source_evaluation_ids: any[]; evaluated_at: string;
};

export type ApprovalView = {
  id: string; target_type: string; target_id: string; policy: string; status: string; requested_by: string;
  requested_at: string; decided_by: string | null; decided_at: string | null; reason: string | null;
  expires_at: string | null; pipeline_run_id: string | null; node_id: string | null; stage_id: string | null; details: JsonObject;
};

export type ReleaseSummary = {
  id: string; release_type: string; status: string; manifest_artifact_id: string; source_commit: string;
  parent_release_id: string | null; limitations: any[]; created_at: string; promoted_at: string | null; superseded_at: string | null;
};
export type ReleaseDetail = ReleaseSummary & {
  metadata: JsonObject; required_gates: string[]; observed_gates: string[]; missing_gates: string[];
  policy_id: string | null; policy_sha256: string | null;
};
export type ReleaseArtifactView = { release_id: string; artifact_id: string; role: string; created_at: string };
export type PromotionDecisionView = {
  id: string; target_type: string; target_id: string; target_kind: string; policy_id: string; policy_version: number;
  policy_sha256: string; expected_state: string; target_state: string; decision: string; execution_status: string;
  requested_by: string; executed_by: string | null; approval_id: string | null; reason: string; created_at: string; executed_at: string | null;
};
export type ModelVersionView = {
  model_name: string; version: string; aliases: string[]; status: string | null; source: string | null; run_id: string | null;
  tags: JsonObject; registration_receipt_artifact_id: string | null; gates: GateSummary[];
};

export type OperationView = {
  id: string; operation_type: string; status: string; requested_by: string; target_type: string; target_id: string;
  prefect_flow_run_id: string | null; pipeline_run_id: string | null; promotion_decision_id: string | null;
  request_id: string; result: JsonObject; error_code: string | null; error_message: string | null; created_at: string;
  started_at: string | null; completed_at: string | null; updated_at: string;
};
export type OperationAccepted = {
  operation_id: string; status: string; target_type: string; target_id: string; prefect_flow_run_id: string | null;
  pipeline_run_id: string | null; replayed: boolean;
};
export type MutationResult = { resource_type: string; resource_id: string; status: string; replayed: boolean; details: JsonObject };

export type RunTriggerRequest = { reason: string; flow_id: string; input_artifact_ids?: Record<string, string>; parameters?: JsonObject };
export type RunCancelRequest = { reason: string; expected_status: "PENDING" | "WAITING_APPROVAL" | "RUNNING" };
export type RunRetryRequest = { reason: string; expected_status: "FAILED" | "CANCELLED"; input_artifact_ids?: Record<string, string>; parameters?: JsonObject };
export type ApprovalDecisionRequest = { reason: string; expected_status?: "REQUESTED" };
export type WaiverGrantRequest = { reason: string; evaluation_id: string; target_kind: string; policy_id: string; approval_id: string; expires_at: string };
export type WaiverRevokeRequest = { reason: string };
export type ArtifactActionRequest = { reason: string; expected_manifest_sha256: string };
export type ReleasePromotionRequest = {
  reason: string; expected_status: "DRAFT" | "CANDIDATE" | "READY_WITH_LIMITATIONS";
  target_status: "READY_WITH_LIMITATIONS" | "CERTIFIED"; approval_id: string; policy_sha256: string;
};
export type ModelPromotionRequest = { reason: string; approval_id: string; policy_sha256: string };
