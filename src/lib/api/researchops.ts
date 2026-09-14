import { apiGet, apiPost, type QueryParams } from "./client";
import type {
  ApprovalDecisionRequest, ApprovalView, ArtifactActionRequest, ArtifactDetail, ArtifactFileView, ArtifactSummary,
  CapabilityResponse, CursorPage, GateEvaluationView, GateSummary, HealthResponse, LineageGraph, ModelPromotionRequest,
  ModelVersionView, MutationResult, OperationAccepted, OperationView, PromotionDecisionView, ReadinessResponse,
  RegistryItem, ReleaseArtifactView, ReleaseDetail, ReleasePromotionRequest, ReleaseSummary, RunCancelRequest,
  RunDetail, RunEventView, RunOutputView, RunReceiptView, RunRetryRequest, RunSummary, RunTriggerRequest,
  StageRunView, VersionResponse, WaiverGrantRequest, WaiverRevokeRequest,
} from "./contracts";

export const researchOpsApi = {
  health: (signal?: AbortSignal) => apiGet<HealthResponse>("healthz", undefined, signal),
  readiness: (signal?: AbortSignal) => apiGet<ReadinessResponse>("readyz", undefined, signal),
  version: (signal?: AbortSignal) => apiGet<VersionResponse>("version", undefined, signal),
  capabilities: (signal?: AbortSignal) => apiGet<CapabilityResponse>("api/v1/capabilities", undefined, signal),
  stages: (signal?: AbortSignal) => apiGet<RegistryItem[]>("api/v1/stages", undefined, signal),
  flows: (signal?: AbortSignal) => apiGet<RegistryItem[]>("api/v1/flows", undefined, signal),
  deployments: (signal?: AbortSignal) => apiGet<RegistryItem[]>("api/v1/deployments", undefined, signal),

  runs: (query?: QueryParams, signal?: AbortSignal) => apiGet<CursorPage<RunSummary>>("api/v1/runs", query, signal),
  run: (id: string, signal?: AbortSignal) => apiGet<RunDetail>(`api/v1/runs/${encodeURIComponent(id)}`, undefined, signal),
  runStages: (id: string, signal?: AbortSignal) => apiGet<StageRunView[]>(`api/v1/runs/${encodeURIComponent(id)}/stages`, undefined, signal),
  runEvents: (id: string, signal?: AbortSignal) => apiGet<RunEventView[]>(`api/v1/runs/${encodeURIComponent(id)}/events`, undefined, signal),
  runOutputs: (id: string, signal?: AbortSignal) => apiGet<RunOutputView[]>(`api/v1/runs/${encodeURIComponent(id)}/outputs`, undefined, signal),
  runReceipt: (id: string, signal?: AbortSignal) => apiGet<RunReceiptView>(`api/v1/runs/${encodeURIComponent(id)}/receipt`, undefined, signal),

  artifacts: (query?: QueryParams, signal?: AbortSignal) => apiGet<CursorPage<ArtifactSummary>>("api/v1/artifacts", query, signal),
  artifact: (id: string, signal?: AbortSignal) => apiGet<ArtifactDetail>(`api/v1/artifacts/${encodeURIComponent(id)}`, undefined, signal),
  artifactFiles: (id: string, signal?: AbortSignal) => apiGet<ArtifactFileView[]>(`api/v1/artifacts/${encodeURIComponent(id)}/files`, undefined, signal),
  artifactLineage: (id: string, query?: QueryParams, signal?: AbortSignal) => apiGet<LineageGraph>(`api/v1/artifacts/${encodeURIComponent(id)}/lineage`, query, signal),
  artifactGates: (id: string, signal?: AbortSignal) => apiGet<GateSummary[]>(`api/v1/artifacts/${encodeURIComponent(id)}/gates`, undefined, signal),
  artifactReleases: (id: string, signal?: AbortSignal) => apiGet<ReleaseArtifactView[]>(`api/v1/artifacts/${encodeURIComponent(id)}/releases`, undefined, signal),

  gates: (query?: QueryParams, signal?: AbortSignal) => apiGet<CursorPage<GateSummary>>("api/v1/gates", query, signal),
  gate: (id: string, signal?: AbortSignal) => apiGet<GateSummary>(`api/v1/gates/${encodeURIComponent(id)}`, undefined, signal),
  gateHistory: (id: string, signal?: AbortSignal) => apiGet<GateEvaluationView[]>(`api/v1/gates/${encodeURIComponent(id)}/history`, undefined, signal),
  gateEvaluation: (id: string, signal?: AbortSignal) => apiGet<GateEvaluationView>(`api/v1/gate-evaluations/${encodeURIComponent(id)}`, undefined, signal),
  scopeGates: (scopeType: string, scopeId: string, signal?: AbortSignal) => apiGet<GateSummary[]>(`api/v1/scopes/${encodeURIComponent(scopeType)}/${encodeURIComponent(scopeId)}/gates`, undefined, signal),

  approvals: (query?: QueryParams, signal?: AbortSignal) => apiGet<CursorPage<ApprovalView>>("api/v1/approvals", query, signal),
  approval: (id: string, signal?: AbortSignal) => apiGet<ApprovalView>(`api/v1/approvals/${encodeURIComponent(id)}`, undefined, signal),

  releases: (query?: QueryParams, signal?: AbortSignal) => apiGet<CursorPage<ReleaseSummary>>("api/v1/releases", query, signal),
  release: (id: string, signal?: AbortSignal) => apiGet<ReleaseDetail>(`api/v1/releases/${encodeURIComponent(id)}`, undefined, signal),
  releaseArtifacts: (id: string, signal?: AbortSignal) => apiGet<ReleaseArtifactView[]>(`api/v1/releases/${encodeURIComponent(id)}/artifacts`, undefined, signal),
  releaseGates: (id: string, signal?: AbortSignal) => apiGet<GateSummary[]>(`api/v1/releases/${encodeURIComponent(id)}/gates`, undefined, signal),
  releasePromotionDecisions: (id: string, signal?: AbortSignal) => apiGet<PromotionDecisionView[]>(`api/v1/releases/${encodeURIComponent(id)}/promotion-decisions`, undefined, signal),

  modelVersions: (name: string, signal?: AbortSignal) => apiGet<ModelVersionView[]>(`api/v1/models/${encodeURIComponent(name)}/versions`, undefined, signal),
  modelVersion: (name: string, version: string, signal?: AbortSignal) => apiGet<ModelVersionView>(`api/v1/models/${encodeURIComponent(name)}/versions/${encodeURIComponent(version)}`, undefined, signal),

  operations: (query?: QueryParams, signal?: AbortSignal) => apiGet<CursorPage<OperationView>>("api/v1/operations", query, signal),
  operation: (id: string, signal?: AbortSignal) => apiGet<OperationView>(`api/v1/operations/${encodeURIComponent(id)}`, undefined, signal),

  triggerRun: (body: RunTriggerRequest, key: string) => apiPost<OperationAccepted>("api/v1/runs", body, key),
  cancelRun: (id: string, body: RunCancelRequest, key: string) => apiPost<OperationAccepted>(`api/v1/runs/${encodeURIComponent(id)}/cancel`, body, key),
  retryRun: (id: string, body: RunRetryRequest, key: string) => apiPost<OperationAccepted>(`api/v1/runs/${encodeURIComponent(id)}/retry`, body, key),
  approve: (id: string, body: ApprovalDecisionRequest, key: string) => apiPost<MutationResult>(`api/v1/approvals/${encodeURIComponent(id)}/approve`, body, key),
  reject: (id: string, body: ApprovalDecisionRequest, key: string) => apiPost<MutationResult>(`api/v1/approvals/${encodeURIComponent(id)}/reject`, body, key),
  grantWaiver: (id: string, body: WaiverGrantRequest, key: string) => apiPost<MutationResult>(`api/v1/gates/${encodeURIComponent(id)}/waivers`, body, key),
  revokeWaiver: (id: string, body: WaiverRevokeRequest, key: string) => apiPost<MutationResult>(`api/v1/waivers/${encodeURIComponent(id)}/revoke`, body, key),
  verifyArtifact: (id: string, body: ArtifactActionRequest, key: string) => apiPost<MutationResult>(`api/v1/artifacts/${encodeURIComponent(id)}/verifications`, body, key),
  reevaluateArtifact: (id: string, body: ArtifactActionRequest, key: string) => apiPost<MutationResult>(`api/v1/artifacts/${encodeURIComponent(id)}/evaluations`, body, key),
  promoteRelease: (id: string, body: ReleasePromotionRequest, key: string) => apiPost<OperationAccepted>(`api/v1/releases/${encodeURIComponent(id)}/promotions`, body, key),
  promoteModel: (name: string, version: string, body: ModelPromotionRequest, key: string) => apiPost<OperationAccepted>(`api/v1/models/${encodeURIComponent(name)}/versions/${encodeURIComponent(version)}/promotions`, body, key),
};

export const RESEARCHOPS_OPERATION_IDS = [
  "health","readiness","version","get_capabilities","list_stages","list_flows","list_deployments",
  "list_runs","get_run","list_run_stages","list_run_events","list_run_outputs","get_run_receipt",
  "list_artifacts","get_artifact","list_artifact_files","get_artifact_lineage","list_artifact_gates","list_artifact_releases",
  "list_gates","get_gate","get_gate_history","get_gate_evaluation","list_scope_gates",
  "list_approvals","get_approval","list_releases","get_release","list_release_artifacts","list_release_gates","list_release_promotion_decisions",
  "list_model_versions","get_model_version","list_control_operations","get_control_operation",
  "trigger_run","cancel_run","retry_run","approve_request","reject_request","grant_gate_waiver","revoke_gate_waiver",
  "verify_artifact","reevaluate_artifact","promote_release","promote_model_version",
] as const;
