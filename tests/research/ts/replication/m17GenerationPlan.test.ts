import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createEvidencePackage } from "../narrative/fixtures";
import type { EvidenceLevel, EvidencePackage } from "../../../../research/ts/narrative/index";
import { buildFreddieGenerationPlan } from "../../../../research/ts/replication/generationPlan";
import { preflightFreddieGenerationModel } from "../../../../research/ts/replication/generationExecution";
import { assertReplicationProtocolMatchesCommonRuntime, REPLICATION_PROTOCOL } from "../../../../research/ts/replication/protocol";
import { getDefaultDeepSeekAtomicClaimExtractorConfig } from "../../../../research/ts/claim_extraction/deepseekAtomicClaimExtractor";
import { createHash } from "node:crypto";

const LEVELS: EvidenceLevel[]=["S0","S1","S2","S3","S4","S5"];

function createFreddieEvidencePackage(level: EvidenceLevel): EvidencePackage {
  const p = createEvidencePackage(level);
  const featurePatch = {
    feature_id: "classic_fico",
    feature_name: "classic_fico",
    display_name: "Điểm FICO cổ điển",
    concept: "borrower_creditworthiness",
    concept_display_name: "Khả năng tín dụng người vay",
    safe_phrase: "Điểm FICO cổ điển góp phần làm tăng rủi ro dự đoán của mô hình.",
  };

  for (const item of p.prompt_payload.selected_evidence) Object.assign(item, featurePatch);
  for (const group of p.prompt_payload.concept_evidence) {
    group.concept = featurePatch.concept;
    group.concept_display_name = featurePatch.concept_display_name;
    group.selected_feature_ids = [featurePatch.feature_id];
    if (group.representative_feature) Object.assign(group.representative_feature, featurePatch);
    for (const item of group.supporting_features ?? []) Object.assign(item, featurePatch);
  }
  for (const slot of p.prompt_payload.backend_explanation_skeleton?.main_factor_slots ?? []) {
    Object.assign(slot, {
      feature_id: featurePatch.feature_id,
      display_name: featurePatch.display_name,
      concept: featurePatch.concept,
      concept_display_name: featurePatch.concept_display_name,
      safe_phrase: featurePatch.safe_phrase,
    });
  }

  p.prompt_payload.constraints.allowed_feature_ids = p.prompt_payload.selected_evidence.flatMap((item) => item.feature_id ? [item.feature_id] : []);
  p.prompt_payload.constraints.allowed_concept_ids = p.prompt_payload.concept_evidence.flatMap((item) => item.concept ? [item.concept] : []);
  return p;
}

test("replication protocol matches frozen common runtime",()=>{assert.doesNotThrow(()=>assertReplicationProtocolMatchesCommonRuntime());assert.deepEqual(REPLICATION_PROTOCOL.generation.models.map(x=>x.model_id),["qwen3_8b","deepseek_v4_flash","phi4_mini_instruct"]);assert.equal(REPLICATION_PROTOCOL.generation.matrix.planned_generations,648);assert.equal(REPLICATION_PROTOCOL.source_experiment.historical_usable_generations,638);});

test("M17A protocol verification is independent of mutable claim runtime env", () => {
  const previous = process.env.DEEPSEEK_CLAIM_MAX_TOKENS;
  process.env.DEEPSEEK_CLAIM_MAX_TOKENS = "12000";
  try {
    assert.equal(getDefaultDeepSeekAtomicClaimExtractorConfig().maxTokens, 12000);
    assert.equal(REPLICATION_PROTOCOL.claim_measurement.extractor_decoding.max_tokens, 3000);
    assert.doesNotThrow(() => assertReplicationProtocolMatchesCommonRuntime());
  } finally {
    if (previous === undefined) delete process.env.DEEPSEEK_CLAIM_MAX_TOKENS;
    else process.env.DEEPSEEK_CLAIM_MAX_TOKENS = previous;
  }
});

test("Freddie M17 plan is exact 36x6x3 and prompt-leakage free",async()=>{const root=await mkdtemp(path.join(os.tmpdir(),"m17plan-"));try{const workspace=path.join(root,"ws");const evidenceDir=path.join(workspace,"data/reports/evidence_exposure/evaluation_36");const manifestDir=path.join(workspace,"data/manifests");await mkdir(evidenceDir,{recursive:true});await mkdir(manifestDir,{recursive:true});const evidence:EvidencePackage[]=[];for(let c=0;c<36;c++){for(const level of LEVELS){const p=createFreddieEvidencePackage(level);p.package_id=`pkg_${level}_case_${c}`;p.source_ir_id=`ir_case_${c}`;p.dataset={dataset_id:"freddie_sflld_2024",dataset_version:"standard_vintage_2024_v1",dataset_fingerprint:"a".repeat(64)};p.experiment={experiment_id:"freddie_sflld_2024_replication_v1"};p.case={case_id:`case_${c}`,source_entity_id:`loan_${c}`,entity_type:"mortgage_loan",case_type:["top_high_risk","low_risk","true_positive","false_positive","false_negative","near_threshold"][c%6]};const sem={positive_label:"high_12m_serious_delinquency_risk",negative_label:"low_12m_serious_delinquency_risk",positive_display_name:"Rủi ro trễ hạn nghiêm trọng cao",negative_display_name:"Rủi ro trễ hạn nghiêm trọng thấp",prediction_subject:"rủi ro trễ hạn thế chấp nghiêm trọng trong 12 tháng",positive_direction_phrase:"làm tăng rủi ro",negative_direction_phrase:"làm giảm rủi ro"};p.target_semantics=sem;p.prompt_payload.target_semantics=sem;evidence.push(p);}}
const evidencePath=path.join(evidenceDir,"evidence_packages_36.jsonl");await writeFile(evidencePath,evidence.map(x=>JSON.stringify(x)).join("\n")+"\n");const hash=createHash("sha256").update(await readFile(evidencePath)).digest("hex");const rel=path.relative(workspace,evidencePath);await writeFile(path.join(manifestDir,"freddie_sflld_2024_m16_evaluation_cohort_receipt_v1.json"),JSON.stringify({stage:"freddie_evaluation_cohort_m16",status:"PASS",dataset_id:"freddie_sflld_2024",invariants:{selected_cases_36:"PASS"},output_fingerprints:{[rel]:hash}}));const result=await buildFreddieGenerationPlan({workspace});assert.equal(result.jobCount,648);const jobs=(await readFile(result.jobsPath,"utf8")).trim().split(/\n/u).map((line) => JSON.parse(line));assert.equal(new Set(jobs.map(x=>x.job_id)).size,648);assert.equal(new Set(jobs.map(x=>x.case_id)).size,36);assert.deepEqual(new Set(jobs.map(x=>x.model_id)),new Set(["qwen3_8b","deepseek_v4_flash","phi4_mini_instruct"]));const prompts=await readFile(result.promptsPath,"utf8");assert.equal(/Home Credit|SK_ID_CURR|AMT_INCOME_TOTAL/u.test(prompts),false);}finally{await rm(root,{recursive:true,force:true});}});


test("Freddie M17 execution preflight re-renders all 216 prompts before provider calls", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "m17preflight-"));
  try {
    const workspace = path.join(root, "ws");
    const evidenceDir = path.join(workspace, "data/reports/evidence_exposure/evaluation_36");
    const manifestDir = path.join(workspace, "data/manifests");
    await mkdir(evidenceDir, { recursive: true });
    await mkdir(manifestDir, { recursive: true });
    const evidence: EvidencePackage[] = [];
    for (let c = 0; c < 36; c += 1) {
      for (const level of LEVELS) {
        const p = createFreddieEvidencePackage(level);
        p.package_id = `pkg_${level}_case_${c}`;
        p.source_ir_id = `ir_case_${c}`;
        p.dataset = { dataset_id: "freddie_sflld_2024", dataset_version: "standard_vintage_2024_v1", dataset_fingerprint: "b".repeat(64) };
        p.experiment = { experiment_id: "freddie_sflld_2024_replication_v1" };
        p.case = { case_id: `case_${c}`, source_entity_id: `loan_${c}`, entity_type: "mortgage_loan", case_type: ["top_high_risk", "low_risk", "true_positive", "false_positive", "false_negative", "near_threshold"][c % 6] };
        const sem = { positive_label: "high_12m_serious_delinquency_risk", negative_label: "low_12m_serious_delinquency_risk", positive_display_name: "Rủi ro trễ hạn nghiêm trọng cao", negative_display_name: "Rủi ro trễ hạn nghiêm trọng thấp", prediction_subject: "rủi ro trễ hạn thế chấp nghiêm trọng trong 12 tháng", positive_direction_phrase: "làm tăng rủi ro", negative_direction_phrase: "làm giảm rủi ro" };
        p.target_semantics = sem; p.prompt_payload.target_semantics = sem; evidence.push(p);
      }
    }
    const evidencePath = path.join(evidenceDir, "evidence_packages_36.jsonl");
    await writeFile(evidencePath, evidence.map((x) => JSON.stringify(x)).join("\n") + "\n");
    const hash = createHash("sha256").update(await readFile(evidencePath)).digest("hex");
    const rel = path.relative(workspace, evidencePath);
    await writeFile(path.join(manifestDir, "freddie_sflld_2024_m16_evaluation_cohort_receipt_v1.json"), JSON.stringify({ stage: "freddie_evaluation_cohort_m16", status: "PASS", dataset_id: "freddie_sflld_2024", invariants: { selected_cases_36: "PASS" }, output_fingerprints: { [rel]: hash } }));
    await buildFreddieGenerationPlan({ workspace });
    const preflight = await preflightFreddieGenerationModel({ workspace, modelId: "qwen3_8b" });
    assert.equal(preflight.plannedCells, 216);
    assert.equal(preflight.promptParityCells, 216);
  } finally { await rm(root, { recursive: true, force: true }); }
});
