import { createHash } from "node:crypto";
import type { CanonicalGenerationRow, JsonObject } from "../../../contracts/llm-validation";
import {
  CLAIM_SUBTYPES_BY_TYPE,
  type AtomicClaimRecord,
  type AtomicClaimRecordV3,
  type ClaimSubtype,
  type ClaimType,
} from "../../../contracts/validation-claims";
import { readJsonlStrict, writeJsonAtomic, writeJsonlAtomic } from "../canonicalization/io";
import { buildSemanticSignature } from "../claim_extraction/claimPostprocessor";
import { buildGenerationTextDocument } from "../claim_extraction/generationTextAdapter";
import { classifyClaimSemantics, classifyClaimSubtype } from "../claim_finalization/claimSubtype";
import { assertClaimCompatible } from "../claim_finalization/claimTypeCompatibility";

export const FREDDIE_SEMANTIC_FINALIZER_VERSION = "freddie_semantic_claim_finalizer_v1.0.0";
export const FREDDIE_SEMANTIC_POLICY_VERSION = "freddie_semantic_migration_policy_v1";

type Working = Omit<AtomicClaimRecord, "claim_schema_version" | "claim_type"> & {
  claim_schema_version: "claims_v3";
  parent_claim_id: string;
  claim_type: ClaimType;
  claim_subtype: ClaimSubtype;
  proposition_status: "COMPLETE";
  source_start: number;
  source_end: number;
  finalizer_version: string;
  finalization_policy_version: string;
};

type Target = {
  claim_type: ClaimType;
  claim_subtype: ClaimSubtype;
  subject_type: AtomicClaimRecord["subject_type"];
  feature_id: string | null;
  concept_id: string | null;
  direction: AtomicClaimRecord["direction"];
  magnitude: AtomicClaimRecord["magnitude"];
  numeric_role_override?: AtomicClaimRecord["numeric_role"];
};

type Resolution = {
  target: Target;
  migrated: AtomicClaimRecordV3;
  mode: string;
};

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const generationsInput = await readJsonlStrict<JsonObject>(required(args, "generation-index"));
  const historicalInput = await readJsonlStrict<AtomicClaimRecord>(required(args, "claims-v2"));
  const generations = generationsInput.records.map((r) => r.value as unknown as CanonicalGenerationRow);
  if (generations.length !== 648) throw new Error(`Freddie semantic migration requires 648 canonical generations; found ${generations.length}.`);
  const generationById = uniqueMap(generations, (x) => x.generation_id, "canonical generation");
  const historical = historicalInput.records.map((r) => r.value);
  const finalClaims: AtomicClaimRecordV3[] = [];
  const changes: JsonObject[] = [];
  let retyped = 0;
  const migrationModes: Record<string, number> = {};
  for (const old of historical) {
    if (old.claim_schema_version !== "claims_v2") throw new Error(`Expected claims_v2 input: ${old.claim_id}`);
    const resolved = resolveCompatibleMigration(old);
    const target = resolved.target;
    const migrated = resolved.migrated;
    migrationModes[resolved.mode] = (migrationModes[resolved.mode] ?? 0) + 1;
    if (target.claim_type !== old.claim_type) retyped += 1;
    finalClaims.push(migrated);
    const stable = JSON.stringify({ generation_id: old.generation_id, parent_claim_id: old.claim_id, new_claim_id: migrated.claim_id });
    changes.push({
      change_schema_version: "freddie_claim_finalization_change_v1",
      change_id: `claim_change_${sha256(stable).slice(0,32)}`,
      generation_id: old.generation_id,
      action: "UPDATE",
      semantic_operation: resolved.mode,
      historical_claim_id: old.claim_id,
      new_claim_id: migrated.claim_id,
      changed_fields: diffFields(old as unknown as JsonObject, migrated as unknown as JsonObject),
      old_claim: old as unknown as JsonObject,
      new_claim: migrated as unknown as JsonObject,
    });
  }
  reindex(finalClaims);
  assertUniqueIds(finalClaims);
  assertUniqueSignatures(finalClaims);
  auditSourceSpans(finalClaims, generationById);
  const claimsOut = await writeJsonlAtomic(required(args, "claims-output"), finalClaims);
  const changesOut = await writeJsonlAtomic(required(args, "changes-output"), changes);
  const typeCounts = countBy(finalClaims, (c) => c.claim_type);
  const subtypeCounts = countBy(finalClaims, (c) => `${c.claim_type}:${c.claim_subtype}`);
  const summary = {
    schema_version: "freddie_semantic_finalization_summary_v1",
    finalizer_version: FREDDIE_SEMANTIC_FINALIZER_VERSION,
    finalization_policy_version: FREDDIE_SEMANTIC_POLICY_VERSION,
    deterministic: true,
    provider_calls_made: 0,
    claims_v2_count: historical.length,
    claims_v3_count: finalClaims.length,
    retyped_claim_count: retyped,
    compatibility_fallback_count: historical.length - (migrationModes.ACTIVE_CLASSIFIER ?? 0),
    migration_mode_counts: Object.fromEntries(Object.entries(migrationModes).sort(([a], [b]) => a.localeCompare(b))),
    dropped_claim_count: 0,
    added_claim_count: 0,
    source_span_mismatch_count: 0,
    claim_type_counts: typeCounts,
    claim_subtype_counts: subtypeCounts,
    output_claims_sha256: claimsOut.sha256,
  };
  await writeJsonAtomic(required(args, "summary-output"), summary);
  await writeJsonAtomic(required(args, "manifest-output"), {
    schema_version: "freddie_semantic_finalization_manifest_v1",
    deterministic: true,
    provider_calls_made: 0,
    finalizer_version: FREDDIE_SEMANTIC_FINALIZER_VERSION,
    finalization_policy_version: FREDDIE_SEMANTIC_POLICY_VERSION,
    lineage: { source_claim_schema_version: "claims_v2", output_claim_schema_version: "claims_v3", migration_mode: "active_classifier_no_dataset_specific_manual_corrections" },
    inputs: { generation_index: { path: generationsInput.path, sha256: generationsInput.sha256, record_count: generationsInput.records.length }, claims_v2: { path: historicalInput.path, sha256: historicalInput.sha256, record_count: historical.length } },
    outputs: { claims_v3: claimsOut, changes: changesOut },
    invariants: { unique_claim_ids: true, unique_semantic_signatures_within_generation: true, source_span_mismatch_count: 0, claim_count_preserved: finalClaims.length === historical.length },
  });
  console.log(`FREDDIE_SEMANTIC_MIGRATION=PASS claims_v2=${historical.length} claims_v3=${finalClaims.length} retyped=${retyped}`);
}

function resolveCompatibleMigration(old: AtomicClaimRecord): Resolution {
  const candidates: Array<{ mode: string; target: Target }> = [
    ...intrinsicUnresolvedTargets(old),
    { mode: "ACTIVE_CLASSIFIER", target: classificationTarget(old, old.claim_type) },
    ...compatibilityFallbackTargets(old),
  ];
  const errors: string[] = [];
  const seen = new Set<string>();
  for (const candidate of candidates) {
    const key = JSON.stringify(candidate.target);
    if (seen.has(key)) continue;
    seen.add(key);
    const migrated = migrate(old, candidate.target);
    try {
      assertClaimCompatible(migrated);
      return { ...candidate, migrated };
    } catch (error) {
      errors.push(`${candidate.mode}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  throw new Error(
    `No compatibility-preserving semantic migration for ${old.claim_id}: ${errors.join(" | ")}`,
  );
}

function intrinsicUnresolvedTargets(
  old: AtomicClaimRecord,
): Array<{ mode: string; target: Target }> {
  // A magnitude claim with no asserted magnitude is not an exact strength claim.
  // Route it to the validator's existing unresolved-semantic path instead of
  // allowing compareMagnitude() to treat an unknown value as an exact match.
  if (
    old.claim_type === "magnitude"
    && (old.magnitude === null || old.magnitude === "unknown")
  ) {
    return [{
      mode: "INTRINSIC_UNKNOWN_MAGNITUDE_TO_UNRESOLVED",
      target: forcedTarget(old, "magnitude", "UNRESOLVED_MAGNITUDE"),
    }];
  }
  return [];
}

function compatibilityFallbackTargets(
  old: AtomicClaimRecord,
): Array<{ mode: string; target: Target }> {
  const candidates: Array<{ mode: string; target: Target }> = [];

  if (old.source_section === "prediction_summary") {
    if (
      old.claim_type === "ranking"
      || old.claim_type === "distributed_evidence"
    ) {
      candidates.push({
        mode: "COMPAT_PREDICTION_SUMMARY_TO_DISTRIBUTED",
        target: classificationTarget(old, "distributed_evidence"),
      });
      candidates.push({
        mode: "COMPAT_PREDICTION_SUMMARY_TO_UNRESOLVED_DISTRIBUTED",
        target: forcedTarget(old, "distributed_evidence", "UNRESOLVED_DISTRIBUTED_EVIDENCE"),
      });
    }
    if (old.claim_type === "magnitude") {
      candidates.push({
        mode: "COMPAT_PREDICTION_SUMMARY_MAGNITUDE_TO_UNRESOLVED_DISTRIBUTED",
        target: forcedTarget(old, "distributed_evidence", "UNRESOLVED_DISTRIBUTED_EVIDENCE"),
      });
    }
    if (old.claim_type === "recommendation") {
      candidates.push({
        mode: "COMPAT_PREDICTION_SUMMARY_RECOMMENDATION_TO_LIMITATION",
        target: classificationTarget(old, "limitation"),
      });
      candidates.push({
        mode: "COMPAT_PREDICTION_SUMMARY_RECOMMENDATION_TO_UNRESOLVED_LIMITATION",
        target: forcedTarget(old, "limitation", "UNRESOLVED_LIMITATION"),
      });
    }
  }

  if (
    old.source_section === "distributed_evidence_note"
    && old.claim_type === "ranking"
  ) {
    candidates.push({
      mode: "COMPAT_DISTRIBUTED_NOTE_RANKING_TO_DISTRIBUTED",
      target: classificationTarget(old, "distributed_evidence"),
    });
    candidates.push({
      mode: "COMPAT_DISTRIBUTED_NOTE_RANKING_TO_UNRESOLVED_DISTRIBUTED",
      target: forcedTarget(old, "distributed_evidence", "UNRESOLVED_DISTRIBUTED_EVIDENCE"),
    });
  }

  if (old.source_section === "uncertainty_note") {
    if (old.claim_type === "numeric") {
      candidates.push({
        mode: "COMPAT_UNCERTAINTY_NUMERIC_TO_OTHER_NUMERIC",
        target: {
          ...forcedTarget(old, "numeric", "OTHER_NUMERIC"),
          numeric_role_override: "other",
        },
      });
    }
    if (old.claim_type === "causal" || old.claim_type === "magnitude") {
      candidates.push({
        mode: "COMPAT_UNCERTAINTY_NOTE_TO_UNCERTAINTY",
        target: classificationTarget(old, "uncertainty"),
      });
      candidates.push({
        mode: "COMPAT_UNCERTAINTY_NOTE_TO_UNRESOLVED_UNCERTAINTY",
        target: forcedTarget(old, "uncertainty", "UNRESOLVED_UNCERTAINTY"),
      });
    }
    if (old.claim_type === "distributed_evidence") {
      candidates.push({
        mode: "COMPAT_UNCERTAINTY_DISTRIBUTED_TO_LIMITATION",
        target: classificationTarget(old, "limitation"),
      });
      candidates.push({
        mode: "COMPAT_UNCERTAINTY_DISTRIBUTED_TO_UNRESOLVED_DISTRIBUTED",
        target: forcedTarget(old, "distributed_evidence", "UNRESOLVED_DISTRIBUTED_EVIDENCE"),
      });
    }
  }

  if (
    old.source_section === "factor_explanation"
    && old.claim_type === "uncertainty"
  ) {
    candidates.push({
      mode: "COMPAT_FACTOR_UNCERTAINTY_TO_ASSOCIATIONAL_CAUSAL",
      target: forcedTarget(old, "causal", "CAUSAL_ATTRIBUTION"),
    });
    candidates.push({
      mode: "COMPAT_FACTOR_UNCERTAINTY_TO_UNRESOLVED_LIMITATION",
      target: forcedTarget(old, "limitation", "UNRESOLVED_LIMITATION"),
    });
  }

  return candidates;
}

function classificationTarget(
  old: AtomicClaimRecord,
  sourceClaimType: ClaimType,
): Target {
  const proxy = { ...old, claim_type: sourceClaimType } as AtomicClaimRecord;
  const classification = classifyClaimSemantics(proxy);
  return targetFromClassification(old, proxy, classification.claim_type, classification.claim_subtype);
}

function forcedTarget(
  old: AtomicClaimRecord,
  claimType: ClaimType,
  claimSubtype: ClaimSubtype,
): Target {
  const proxy = { ...old, claim_type: claimType } as AtomicClaimRecord;
  return targetFromClassification(old, proxy, claimType, claimSubtype);
}

function targetFromClassification(
  old: AtomicClaimRecord,
  proxy: AtomicClaimRecord,
  claimType: ClaimType,
  claimSubtype: ClaimSubtype,
): Target {
  const preserveEntity =
    claimType === "feature_presence"
    || claimType === "feature_direction"
    || claimType === "concept_presence"
    || claimType === "concept_direction"
    || claimType === "ranking"
    || claimType === "magnitude"
    || claimType === "numeric"
    || claimType === "causal";
  return {
    claim_type: claimType,
    claim_subtype: claimSubtype,
    subject_type: claimType === proxy.claim_type
      ? normalizedSubjectType(proxy)
      : targetSubjectType(claimType),
    feature_id: preserveEntity ? old.feature_id : null,
    concept_id: preserveEntity ? old.concept_id : null,
    direction: old.direction,
    magnitude: claimType === "magnitude" ? old.magnitude : null,
  };
}

function migrate(old: AtomicClaimRecord, target: Target): AtomicClaimRecordV3 {
  const numeric = predictionNumericFact(old, target);
  const working: Working = {
    ...old,
    claim_schema_version: "claims_v3",
    parent_claim_id: old.claim_id,
    claim_type: target.claim_type,
    claim_subtype: target.claim_subtype,
    proposition_status: "COMPLETE",
    source_start: old.source_span_start,
    source_end: old.source_span_end,
    subject_type: target.subject_type,
    feature_id: target.feature_id,
    concept_id: target.concept_id,
    direction: target.direction,
    magnitude: target.magnitude,
    numeric_value: numeric.value,
    numeric_unit: numeric.unit,
    numeric_role: numeric.role,
    model_normalized_claim_key: semanticModelKey(old, target),
    finalizer_version: FREDDIE_SEMANTIC_FINALIZER_VERSION,
    finalization_policy_version: FREDDIE_SEMANTIC_POLICY_VERSION,
    semantic_signature: "",
    normalized_claim_key: "",
    claim_id: "",
  };
  const signature = `${buildSemanticSignature(working)}|subtype:${target.claim_subtype}`;
  working.semantic_signature = signature;
  working.normalized_claim_key = signature;
  working.claim_id = `claim_${sha256(`${working.generation_id}|${signature}|${working.source_start}`).slice(0,32)}`;
  return narrowV3Claim(working);
}

function predictionNumericFact(old: AtomicClaimRecord, target: Target): { value: number | null; unit: string | null; role: AtomicClaimRecord["numeric_role"] } {
  if (target.claim_type === "numeric") return { value: old.numeric_value, unit: old.numeric_unit, role: target.numeric_role_override ?? old.numeric_role };
  if (target.claim_type !== "prediction") return { value: null, unit: null, role: null };
  const percentage = old.source_text.match(/(\d+(?:[.,]\d+)?)\s*%/u);
  if (!percentage?.[1]) return { value: null, unit: null, role: null };
  return { value: Number(percentage[1].replace(",", ".")) / 100, unit: "probability", role: "prediction_score" };
}

function semanticModelKey(old: AtomicClaimRecord, target: Target): string | null {
  // Preserve the extractor's proposition key across schema migration. The active
  // classifier may legitimately collapse two old claim families onto one v3
  // family; retaining the original proposition key keeps those distinct atomic
  // propositions distinct without inventing claim-ID-specific exceptions.
  if (old.model_normalized_claim_key) return old.model_normalized_claim_key;
  if (target.feature_id) return `feature:${target.feature_id}`;
  if (target.concept_id) return `concept:${target.concept_id}`;
  const classification = classifyClaimSemantics(old);
  if (target.claim_type !== classification.claim_type || target.claim_subtype !== classifyClaimSubtype(old)) {
    return `${target.claim_type}:${target.claim_subtype.toLocaleLowerCase("en-US")}`;
  }
  return null;
}

function normalizedSubjectType(claim: AtomicClaimRecord): AtomicClaimRecord["subject_type"] {
  switch (claim.claim_type) {
    case "prediction": return "prediction";
    case "feature_presence": case "feature_direction": return "feature";
    case "ranking": return claim.concept_id ? "concept" : "feature";
    case "concept_presence": case "concept_direction": return "concept";
    case "distributed_evidence": return "evidence";
    case "recommendation": case "limitation": return "narrative";
    case "numeric": if (claim.concept_id) return "concept"; if (claim.numeric_role === "prediction_score" || claim.numeric_role === "decision_threshold") return "prediction"; if (claim.numeric_role === "feature_value" || claim.numeric_role === "rank") return "feature"; return "evidence";
    case "magnitude": if (claim.feature_id) return "feature"; if (claim.concept_id) return "concept"; return "evidence";
    case "causal": return claim.subject_type === "none" ? "narrative" : claim.subject_type;
    default: return claim.subject_type;
  }
}
function targetSubjectType(type: ClaimType): AtomicClaimRecord["subject_type"] { switch(type){ case "prediction": return "prediction"; case "feature_presence": case "feature_direction": case "ranking": return "feature"; case "concept_presence": case "concept_direction": return "concept"; case "distributed_evidence": case "magnitude": return "evidence"; case "recommendation": case "limitation": return "narrative"; default: return "none"; } }

function narrowV3Claim(claim: Working): AtomicClaimRecordV3 { switch(claim.claim_type){ case "prediction": return narrow(claim,"prediction",CLAIM_SUBTYPES_BY_TYPE.prediction); case "feature_presence": return narrow(claim,"feature_presence",CLAIM_SUBTYPES_BY_TYPE.feature_presence); case "feature_direction": return narrow(claim,"feature_direction",CLAIM_SUBTYPES_BY_TYPE.feature_direction); case "concept_presence": return narrow(claim,"concept_presence",CLAIM_SUBTYPES_BY_TYPE.concept_presence); case "concept_direction": return narrow(claim,"concept_direction",CLAIM_SUBTYPES_BY_TYPE.concept_direction); case "magnitude": return narrow(claim,"magnitude",CLAIM_SUBTYPES_BY_TYPE.magnitude); case "ranking": return narrow(claim,"ranking",CLAIM_SUBTYPES_BY_TYPE.ranking); case "numeric": return narrow(claim,"numeric",CLAIM_SUBTYPES_BY_TYPE.numeric); case "causal": return narrow(claim,"causal",CLAIM_SUBTYPES_BY_TYPE.causal); case "uncertainty": return narrow(claim,"uncertainty",CLAIM_SUBTYPES_BY_TYPE.uncertainty); case "distributed_evidence": return narrow(claim,"distributed_evidence",CLAIM_SUBTYPES_BY_TYPE.distributed_evidence); case "recommendation": return narrow(claim,"recommendation",CLAIM_SUBTYPES_BY_TYPE.recommendation); case "limitation": return narrow(claim,"limitation",CLAIM_SUBTYPES_BY_TYPE.limitation); } }
function narrow<Type extends ClaimType, Subs extends readonly ClaimSubtype[]>(claim: Working, type: Type, subtypes: Subs): AtomicClaimRecordV3 { if(!subtypes.includes(claim.claim_subtype)) throw new Error(`Subtype ${claim.claim_subtype} incompatible with ${type}.`); return {...claim,claim_type:type,claim_subtype:claim.claim_subtype} as AtomicClaimRecordV3; }

function reindex(claims: AtomicClaimRecordV3[]): void { const groups=groupBy(claims,c=>c.generation_id); for(const group of groups.values()){ group.sort((a,b)=>a.source_start-b.source_start||a.source_end-b.source_end||a.claim_id.localeCompare(b.claim_id)); group.forEach((c,i)=>{c.local_claim_index=i+1;}); } claims.sort((a,b)=>a.generation_id.localeCompare(b.generation_id)||a.local_claim_index-b.local_claim_index); }
function auditSourceSpans(claims: readonly AtomicClaimRecordV3[], generations: ReadonlyMap<string, CanonicalGenerationRow>): void { for(const claim of claims){ const row=generations.get(claim.generation_id); if(!row) throw new Error(`Missing generation for final claim ${claim.claim_id}.`); const doc=buildGenerationTextDocument(row); const reconstructed=doc.generation_text.slice(claim.source_start,claim.source_end); if(reconstructed!==claim.source_text || sha256(reconstructed)!==claim.source_text_sha256 || doc.source_input_sha256!==claim.source_input_sha256) throw new Error(`Source lineage mismatch for ${claim.claim_id}.`); } }
function assertUniqueIds(claims: readonly AtomicClaimRecordV3[]): void { const s=new Set<string>(); for(const c of claims){ if(s.has(c.claim_id)) throw new Error(`Duplicate claims_v3 claim_id: ${c.claim_id}`); s.add(c.claim_id);} }
function assertUniqueSignatures(claims: readonly AtomicClaimRecordV3[]): void { const m=new Map<string,Set<string>>(); for(const c of claims){ const s=m.get(c.generation_id)??new Set<string>(); if(s.has(c.semantic_signature)) throw new Error(`Duplicate semantic signature in ${c.generation_id}: ${c.semantic_signature}`); s.add(c.semantic_signature); m.set(c.generation_id,s);} }
function uniqueMap<T>(xs: readonly T[], key:(x:T)=>string,label:string): Map<string,T>{ const m=new Map<string,T>(); for(const x of xs){const k=key(x); if(m.has(k)) throw new Error(`Duplicate ${label}: ${k}`); m.set(k,x);} return m; }
function groupBy<T>(xs: readonly T[], key:(x:T)=>string): Map<string,T[]>{ const m=new Map<string,T[]>(); for(const x of xs){const k=key(x); const g=m.get(k)??[]; g.push(x); m.set(k,g);} return m; }
function countBy<T>(xs: readonly T[], key:(x:T)=>string): Record<string,number>{ const o:Record<string,number>={}; for(const x of xs){const k=key(x); o[k]=(o[k]??0)+1;} return Object.fromEntries(Object.entries(o).sort(([a],[b])=>a.localeCompare(b))); }
function diffFields(a: JsonObject,b: JsonObject): string[]{ return [...new Set([...Object.keys(a),...Object.keys(b)])].filter(k=>JSON.stringify(a[k])!==JSON.stringify(b[k])).sort(); }
function sha256(value:string):string{return createHash("sha256").update(value).digest("hex");}
function parseArgs(values:string[]):Map<string,string>{const m=new Map<string,string>(); for(let i=0;i<values.length;i+=2){const k=values[i],v=values[i+1]; if(!k?.startsWith("--")||v===undefined||v.startsWith("--")) throw new Error(`Invalid CLI arguments near ${k??"end"}.`); m.set(k.slice(2),v);} return m;}
function required(args:ReadonlyMap<string,string>,key:string):string{const v=args.get(key)?.trim(); if(!v) throw new Error(`Missing required argument: --${key}`); return v;}
main().catch((error:unknown)=>{console.error(error instanceof Error?error.stack??error.message:String(error));process.exitCode=1;});
