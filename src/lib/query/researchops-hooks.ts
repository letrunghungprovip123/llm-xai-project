"use client";

import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { researchOpsApi } from "@/lib/api/researchops";
import type { QueryParams } from "@/lib/api/client";
import type {
  ApprovalDecisionRequest,
  ArtifactActionRequest,
  ModelPromotionRequest,
  ReleasePromotionRequest,
  RunCancelRequest,
  RunRetryRequest,
  RunTriggerRequest,
  WaiverGrantRequest,
  WaiverRevokeRequest,
} from "@/lib/api/contracts";
import { qk } from "./keys";
import { isLiveRunStatus, isTerminalOperationStatus } from "@/lib/status/status-registry";

const fresh = { staleTime: 10_000, refetchOnWindowFocus: true } as const;
const stable = { staleTime: 60_000, refetchOnWindowFocus: false } as const;

type CommandVariables<TBody> = { body: TBody; key: string };
type ResourceCommandVariables<TBody> = CommandVariables<TBody> & { id: string };
type ModelPromotionVariables = CommandVariables<ModelPromotionRequest> & { name: string; version: string };

export const useHealth = () => useQuery({ queryKey: qk.health, queryFn: ({ signal }) => researchOpsApi.health(signal), ...fresh, retry: 1 });
export const useReadiness = () => useQuery({ queryKey: qk.readiness, queryFn: ({ signal }) => researchOpsApi.readiness(signal), ...fresh, refetchInterval: 20_000, retry: 1 });
export const useVersion = () => useQuery({ queryKey: qk.version, queryFn: ({ signal }) => researchOpsApi.version(signal), ...stable });
export const useCapabilities = () => useQuery({ queryKey: qk.capabilities, queryFn: ({ signal }) => researchOpsApi.capabilities(signal), ...stable });
export const useStages = () => useQuery({ queryKey: qk.stages, queryFn: ({ signal }) => researchOpsApi.stages(signal), ...stable });
export const useFlows = () => useQuery({ queryKey: qk.flows, queryFn: ({ signal }) => researchOpsApi.flows(signal), ...stable });
export const useDeployments = () => useQuery({ queryKey: qk.deployments, queryFn: ({ signal }) => researchOpsApi.deployments(signal), ...stable });

export const useRuns = (query: QueryParams) => useQuery({ queryKey: qk.runs(query), queryFn: ({ signal }) => researchOpsApi.runs(query, signal), ...fresh });
export const useRun = (id: string) => useQuery({
  queryKey: qk.run(id),
  queryFn: ({ signal }) => researchOpsApi.run(id, signal),
  enabled: !!id,
  ...fresh,
  refetchInterval: (query) => isLiveRunStatus(query.state.data?.status) ? 4_000 : false,
});
export const useRunStages = (id: string, live = false) => useQuery({ queryKey: qk.runStages(id), queryFn: ({ signal }) => researchOpsApi.runStages(id, signal), enabled: !!id, ...fresh, refetchInterval: live ? 4_000 : false });
export const useRunEvents = (id: string, live = false) => useQuery({ queryKey: qk.runEvents(id), queryFn: ({ signal }) => researchOpsApi.runEvents(id, signal), enabled: !!id, ...fresh, refetchInterval: live ? 8_000 : false });
export const useRunOutputs = (id: string, live = false) => useQuery({ queryKey: qk.runOutputs(id), queryFn: ({ signal }) => researchOpsApi.runOutputs(id, signal), enabled: !!id, ...fresh, refetchInterval: live ? 6_000 : false });
export const useRunReceipt = (id: string) => useQuery({ queryKey: qk.runReceipt(id), queryFn: ({ signal }) => researchOpsApi.runReceipt(id, signal), enabled: !!id, ...stable });

export const useArtifacts = (query: QueryParams) => useQuery({ queryKey: qk.artifacts(query), queryFn: ({ signal }) => researchOpsApi.artifacts(query, signal), ...fresh });
export const useArtifact = (id: string) => useQuery({ queryKey: qk.artifact(id), queryFn: ({ signal }) => researchOpsApi.artifact(id, signal), enabled: !!id, ...fresh });
export const useArtifactFiles = (id: string) => useQuery({ queryKey: qk.artifactFiles(id), queryFn: ({ signal }) => researchOpsApi.artifactFiles(id, signal), enabled: !!id, ...stable });
export const useArtifactLineage = (id: string, query: QueryParams) => useQuery({ queryKey: qk.artifactLineage(id, query), queryFn: ({ signal }) => researchOpsApi.artifactLineage(id, query, signal), enabled: !!id, ...stable });
export const useArtifactGates = (id: string) => useQuery({ queryKey: qk.artifactGates(id), queryFn: ({ signal }) => researchOpsApi.artifactGates(id, signal), enabled: !!id, ...fresh });
export const useArtifactReleases = (id: string) => useQuery({ queryKey: qk.artifactReleases(id), queryFn: ({ signal }) => researchOpsApi.artifactReleases(id, signal), enabled: !!id, ...stable });

export const useGates = (query: QueryParams) => useQuery({ queryKey: qk.gates(query), queryFn: ({ signal }) => researchOpsApi.gates(query, signal), ...fresh });
export const useGate = (id: string) => useQuery({ queryKey: qk.gate(id), queryFn: ({ signal }) => researchOpsApi.gate(id, signal), enabled: !!id, ...fresh });
export const useGateHistory = (id: string) => useQuery({ queryKey: qk.gateHistory(id), queryFn: ({ signal }) => researchOpsApi.gateHistory(id, signal), enabled: !!id, ...fresh });
export const useGateEvaluation = (id: string) => useQuery({ queryKey: qk.evaluation(id), queryFn: ({ signal }) => researchOpsApi.gateEvaluation(id, signal), enabled: !!id, ...fresh });

export const useApprovals = (query: QueryParams) => useQuery({ queryKey: qk.approvals(query), queryFn: ({ signal }) => researchOpsApi.approvals(query, signal), ...fresh });
export const useApproval = (id: string) => useQuery({ queryKey: qk.approval(id), queryFn: ({ signal }) => researchOpsApi.approval(id, signal), enabled: !!id, ...fresh });

export const useReleases = (query: QueryParams) => useQuery({ queryKey: qk.releases(query), queryFn: ({ signal }) => researchOpsApi.releases(query, signal), ...fresh });
export const useRelease = (id: string) => useQuery({ queryKey: qk.release(id), queryFn: ({ signal }) => researchOpsApi.release(id, signal), enabled: !!id, ...fresh });
export const useReleaseArtifacts = (id: string) => useQuery({ queryKey: qk.releaseArtifacts(id), queryFn: ({ signal }) => researchOpsApi.releaseArtifacts(id, signal), enabled: !!id, ...stable });
export const useReleaseGates = (id: string) => useQuery({ queryKey: qk.releaseGates(id), queryFn: ({ signal }) => researchOpsApi.releaseGates(id, signal), enabled: !!id, ...fresh });
export const useReleaseDecisions = (id: string) => useQuery({ queryKey: qk.releaseDecisions(id), queryFn: ({ signal }) => researchOpsApi.releasePromotionDecisions(id, signal), enabled: !!id, ...stable });

export const useModelVersions = (name: string) => useQuery({ queryKey: qk.modelVersions(name), queryFn: ({ signal }) => researchOpsApi.modelVersions(name, signal), enabled: !!name, ...fresh });
export const useModelVersion = (name: string, version: string) => useQuery({ queryKey: qk.modelVersion(name, version), queryFn: ({ signal }) => researchOpsApi.modelVersion(name, version, signal), enabled: !!name && !!version, ...fresh });

export const useOperations = (query: QueryParams) => useQuery({ queryKey: qk.operations(query), queryFn: ({ signal }) => researchOpsApi.operations(query, signal), ...fresh });
export const useOperation = (id: string) => useQuery({
  queryKey: qk.operation(id), queryFn: ({ signal }) => researchOpsApi.operation(id, signal), enabled: !!id, ...fresh,
  refetchInterval: (query) => {
    const status = query.state.data?.status;
    return isTerminalOperationStatus(status) ? false : 2500;
  },
});

export function useResearchOpsMutations() {
  const qc = useQueryClient();

  const invalidate = async (...queryKeys: QueryKey[]) => {
    await Promise.all(
      queryKeys.map((queryKey) => qc.invalidateQueries({ queryKey })),
    );
  };

  return {
    triggerRun: useMutation({
      mutationFn: ({ body, key }: CommandVariables<RunTriggerRequest>) => researchOpsApi.triggerRun(body, key),
      onSuccess: () => invalidate(qk.runsRoot, qk.operationsRoot),
    }),
    cancelRun: useMutation({
      mutationFn: ({ id, body, key }: ResourceCommandVariables<RunCancelRequest>) => researchOpsApi.cancelRun(id, body, key),
      onSuccess: (_data, { id }) => invalidate(qk.run(id), qk.runsRoot, qk.operationsRoot),
    }),
    retryRun: useMutation({
      mutationFn: ({ id, body, key }: ResourceCommandVariables<RunRetryRequest>) => researchOpsApi.retryRun(id, body, key),
      onSuccess: (_data, { id }) => invalidate(qk.run(id), qk.runsRoot, qk.operationsRoot),
    }),
    approve: useMutation({
      mutationFn: ({ id, body, key }: ResourceCommandVariables<ApprovalDecisionRequest>) => researchOpsApi.approve(id, body, key),
      onSuccess: (_data, { id }) => invalidate(qk.approval(id), qk.approvalsRoot, qk.gatesRoot, qk.gateDetailsRoot, qk.releasesRoot, qk.releaseDetailsRoot, qk.runDetailsRoot),
    }),
    reject: useMutation({
      mutationFn: ({ id, body, key }: ResourceCommandVariables<ApprovalDecisionRequest>) => researchOpsApi.reject(id, body, key),
      onSuccess: (_data, { id }) => invalidate(qk.approval(id), qk.approvalsRoot, qk.gatesRoot, qk.gateDetailsRoot, qk.releasesRoot, qk.releaseDetailsRoot, qk.runDetailsRoot),
    }),
    grantWaiver: useMutation({
      mutationFn: ({ id, body, key }: ResourceCommandVariables<WaiverGrantRequest>) => researchOpsApi.grantWaiver(id, body, key),
      onSuccess: (_data, { id }) => invalidate(qk.gate(id), qk.gatesRoot, qk.gateDetailsRoot, qk.releasesRoot, qk.releaseDetailsRoot),
    }),
    revokeWaiver: useMutation({
      mutationFn: ({ id, body, key }: ResourceCommandVariables<WaiverRevokeRequest>) => researchOpsApi.revokeWaiver(id, body, key),
      onSuccess: () => invalidate(qk.gatesRoot, qk.gateDetailsRoot, qk.releasesRoot, qk.releaseDetailsRoot),
    }),
    verifyArtifact: useMutation({
      mutationFn: ({ id, body, key }: ResourceCommandVariables<ArtifactActionRequest>) => researchOpsApi.verifyArtifact(id, body, key),
      onSuccess: (_data, { id }) => invalidate(qk.artifact(id), qk.artifactsRoot, qk.gatesRoot, qk.gateDetailsRoot, qk.releasesRoot, qk.releaseDetailsRoot),
    }),
    reevaluateArtifact: useMutation({
      mutationFn: ({ id, body, key }: ResourceCommandVariables<ArtifactActionRequest>) => researchOpsApi.reevaluateArtifact(id, body, key),
      onSuccess: (_data, { id }) => invalidate(qk.artifact(id), qk.artifactsRoot, qk.gatesRoot, qk.gateDetailsRoot, qk.releasesRoot, qk.releaseDetailsRoot),
    }),
    promoteRelease: useMutation({
      mutationFn: ({ id, body, key }: ResourceCommandVariables<ReleasePromotionRequest>) => researchOpsApi.promoteRelease(id, body, key),
      onSuccess: (_data, { id }) => invalidate(qk.release(id), qk.releasesRoot, qk.operationsRoot),
    }),
    promoteModel: useMutation({
      mutationFn: ({ name, version, body, key }: ModelPromotionVariables) => researchOpsApi.promoteModel(name, version, body, key),
      onSuccess: () => invalidate(qk.modelsRoot, qk.operationsRoot),
    }),
  };
}
