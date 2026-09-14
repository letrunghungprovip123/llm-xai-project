import { createHash } from "node:crypto";

import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../contracts/validation-claims";

/** Selects a stable, coverage-first smoke cohort from official claims. */
export function selectBalancedSmokeClaims(
  claims: readonly AtomicClaimRecord[],
  limit: number,
): AtomicClaimRecord[] {
  if (limit >= claims.length) return [...claims].sort(compareClaims);
  const stable = stableSmokeOrder(claims);
  const selected = new Map<string, AtomicClaimRecord>();
  addDimensionCoverage(stable, selected, limit);
  addBoundaryCoverage(stable, selected, limit);
  addStratifiedRemainder(stable, selected, limit);
  return [...selected.values()].sort(compareClaims);
}

export function compareClaims(
  left: AtomicClaimRecord,
  right: AtomicClaimRecord,
): number {
  return left.claim_id.localeCompare(right.claim_id);
}

function stableSmokeOrder(
  claims: readonly AtomicClaimRecord[],
): AtomicClaimRecord[] {
  return [...claims].sort((left, right) => {
    const byHash = smokeHash(left.claim_id).localeCompare(
      smokeHash(right.claim_id),
    );
    return byHash || compareClaims(left, right);
  });
}

function addDimensionCoverage(
  claims: readonly AtomicClaimRecord[],
  selected: Map<string, AtomicClaimRecord>,
  limit: number,
): void {
  const dimensions: Array<(claim: AtomicClaimRecord) => string> = [
    (claim) => claim.claim_type,
    (claim) => claim.model_id,
    (claim) => claim.evidence_level,
    (claim) => claim.claim_origin,
  ];
  for (const dimension of dimensions) {
    const values = [...new Set(claims.map(dimension))].sort();
    for (const value of values) {
      includeFirst(claims, selected, limit, (claim) => dimension(claim) === value);
    }
  }
}

function addBoundaryCoverage(
  claims: readonly AtomicClaimRecord[],
  selected: Map<string, AtomicClaimRecord>,
  limit: number,
): void {
  const predicates: Array<(claim: AtomicClaimRecord) => boolean> = [
    (claim) => claim.evidence_level === "S0" && claim.claim_type === "prediction",
    (claim) =>
      claim.evidence_level === "S0" &&
      ["feature_presence", "feature_direction"].includes(claim.claim_type),
    (claim) => claim.claim_type === "feature_direction",
    (claim) => claim.claim_type === "concept_direction",
    (claim) => claim.claim_type === "numeric",
    (claim) => claim.claim_type === "ranking",
    (claim) => claim.claim_type === "magnitude",
    (claim) => claim.claim_type === "recommendation",
    (claim) => claim.claim_type === "uncertainty",
  ];
  for (const predicate of predicates) {
    includeFirst(claims, selected, limit, predicate);
  }
}

function addStratifiedRemainder(
  claims: readonly AtomicClaimRecord[],
  selected: Map<string, AtomicClaimRecord>,
  limit: number,
): void {
  const groups = buildStrata(claims);
  for (let depth = 0; selected.size < limit; depth += 1) {
    const added = addDepth(groups, depth, selected, limit);
    if (!added) return;
  }
}

function addDepth(
  groups: readonly AtomicClaimRecord[][],
  depth: number,
  selected: Map<string, AtomicClaimRecord>,
  limit: number,
): boolean {
  let foundCandidate = false;
  for (const group of groups) {
    const candidate = group[depth];
    if (!candidate) continue;
    foundCandidate = true;
    if (selected.has(candidate.claim_id)) continue;
    selected.set(candidate.claim_id, candidate);
    if (selected.size === limit) return true;
  }
  return foundCandidate;
}

function buildStrata(
  claims: readonly AtomicClaimRecord[],
): AtomicClaimRecord[][] {
  const strata = new Map<string, AtomicClaimRecord[]>();
  for (const claim of claims) {
    const key = [
      claim.model_id,
      claim.evidence_level,
      claim.claim_type,
      claim.claim_origin,
    ].join("|");
    const group = strata.get(key) ?? [];
    group.push(claim);
    strata.set(key, group);
  }
  return [...strata.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([, group]) => group);
}

function includeFirst(
  claims: readonly AtomicClaimRecord[],
  selected: Map<string, AtomicClaimRecord>,
  limit: number,
  predicate: (claim: AtomicClaimRecord) => boolean,
): void {
  if (selected.size >= limit) return;
  const found = claims.find(
    (claim) => predicate(claim) && !selected.has(claim.claim_id),
  );
  if (found) selected.set(found.claim_id, found);
}

function smokeHash(claimId: string): string {
  return createHash("sha256").update(`smoke_v2\n${claimId}`).digest("hex");
}
