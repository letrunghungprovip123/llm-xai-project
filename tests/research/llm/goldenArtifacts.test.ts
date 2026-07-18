import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

import type { CanonicalGenerationRow } from "../../../research/llm/canonicalization/index";
import { buildGenerationTextDocument } from "../../../research/llm/claim_extraction/index";
import {
  FROZEN_SELECTION_POLICY,
  assertFrozenSelectionPolicy,
} from "../../../research/llm/selection/index";

const execFileAsync = promisify(execFile);
const repositoryRoot = process.cwd();
const configuredGoldenRoot = process.env.RESEARCH_GOLDEN_ROOT;
const goldenRoot = configuredGoldenRoot
  ? path.resolve(configuredGoldenRoot)
  : repositoryRoot;
const phase0Root = path.join(
  goldenRoot,
  "data/reports/llm_validation/validation_v1/phase0",
);
const goldenAvailable = existsSync(
  path.join(phase0Root, "generation_index.jsonl"),
);

function readJsonl(relativePath: string): Array<Record<string, unknown>> {
  const content = readFileSync(path.join(goldenRoot, relativePath), "utf-8");
  return content
    .split(/\r?\n/u)
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as Record<string, unknown>);
}

function sha256File(relativePath: string): string {
  const content = readFileSync(path.join(goldenRoot, relativePath));
  return createHash("sha256").update(content).digest("hex");
}

test(
  "golden canonical matrix giữ 648/638/10 và 10 truncated S4",
  { skip: !goldenAvailable },
  () => {
    const rows = readJsonl(
      "data/reports/llm_validation/validation_v1/phase0/generation_index.jsonl",
    );
    const usable = rows.filter((row) => row.usable === true);
    const unusable = rows.filter((row) => row.usable === false);

    assert.equal(rows.length, 648);
    assert.equal(usable.length, 638);
    assert.equal(unusable.length, 10);
    assert.equal(
      new Set(rows.map((row) => row.canonical_key)).size,
      rows.length,
    );
    assert.equal(
      new Set(rows.map((row) => row.generation_id)).size,
      rows.length,
    );
    assert.equal(
      unusable.every(
        (row) =>
          row.evidence_level === "S4" && row.truncated_response === true,
      ),
      true,
    );

    const modelCounts = Object.fromEntries(
      ["qwen3_8b", "deepseek_v4_flash", "phi4_mini_instruct"].map(
        (modelId) => {
          const modelRows = rows.filter((row) => row.model_id === modelId);
          return [
            modelId,
            {
              total: modelRows.length,
              usable: modelRows.filter((row) => row.usable === true).length,
            },
          ];
        },
      ),
    );
    assert.deepEqual(modelCounts, {
      qwen3_8b: { total: 216, usable: 216 },
      deepseek_v4_flash: { total: 216, usable: 213 },
      phi4_mini_instruct: { total: 216, usable: 209 },
    });
  },
);

test(
  "case/source/package mapping là nhất quán trên canonical cohort",
  { skip: !goldenAvailable },
  () => {
    const rows = readJsonl(
      "data/reports/llm_validation/validation_v1/phase0/generation_index.jsonl",
    );
    const evidence = readJsonl(
      "data/reports/evidence_exposure/evaluation_36/evidence_packages_36.jsonl",
    );
    const sourceToCase = new Map<string, string>();
    const packageToSource = new Map(
      evidence.map((item) => [String(item.package_id), String(item.source_ir_id)]),
    );

    for (const row of rows) {
      const sourceIrId = String(row.source_ir_id);
      const caseId = String(row.case_id);
      const existingCase = sourceToCase.get(sourceIrId);
      if (existingCase !== undefined) assert.equal(caseId, existingCase);
      sourceToCase.set(sourceIrId, caseId);
      assert.equal(packageToSource.get(String(row.package_id)), sourceIrId);
    }

    assert.equal(sourceToCase.size, 36);
    assert.equal(packageToSource.size, 216);
  },
);

test(
  "contract artifact giữ 602/46 và direction surface chưa implement",
  { skip: !goldenAvailable },
  () => {
    const relativePath =
      "data/reports/llm_validation/validation_v1/contract_validation/generation_contract_metrics.jsonl";
    const rows = readJsonl(relativePath);

    assert.equal(rows.length, 648);
    assert.equal(rows.filter((row) => row.contract_pass === true).length, 602);
    assert.equal(rows.filter((row) => row.contract_pass === false).length, 46);
    assert.equal(
      rows.every((row) => {
        const metrics = row.evidence_reference_metrics as Record<
          string,
          unknown
        >;
        return metrics.direction_surface_match === null;
      }),
      true,
    );
    assert.equal(
      sha256File(relativePath),
      "ff3119aca691257c25117fe56c3bf074fb2f69671b70ed775a3a59e7126ca2ec",
    );
  },
);

test(
  "claim v2.1 giữ attempts, failures, exact spans và nested numeric overlap",
  { skip: !goldenAvailable },
  () => {
    const base =
      "data/reports/llm_validation/validation_v1/claim_extraction_deepseek_v2_1";
    const canonicalRows = readJsonl(
      "data/reports/llm_validation/validation_v1/phase0/generation_index.jsonl",
    );
    const attempts = readJsonl(`${base}/claim_extraction_attempts.jsonl`);
    const claims = readJsonl(`${base}/claims.jsonl`);
    const failures = readJsonl(`${base}/claim_extraction_failures.jsonl`);
    const rowByGeneration = new Map(
      canonicalRows.map((row) => [String(row.generation_id), row]),
    );

    assert.equal(attempts.length, 21);
    assert.equal(attempts.filter((item) => item.status === "SUCCESS").length, 19);
    assert.equal(claims.length, 383);
    assert.equal(new Set(claims.map((claim) => claim.claim_id)).size, 383);
    assert.equal(failures.filter((failure) => failure.attempted === false).length, 10);

    for (const claim of claims) {
      const canonicalRow = rowByGeneration.get(String(claim.generation_id));
      assert.ok(canonicalRow);
      const document = buildGenerationTextDocument(
        canonicalRow as unknown as CanonicalGenerationRow,
      );
      const sourceText = document.generation_text.slice(
        Number(claim.source_span_start),
        Number(claim.source_span_end),
      );
      assert.equal(sourceText, claim.source_text);
    }

    const claimsByGeneration = new Map<string, Array<Record<string, unknown>>>();
    for (const claim of claims) {
      const generationId = String(claim.generation_id);
      const current = claimsByGeneration.get(generationId) ?? [];
      current.push(claim);
      claimsByGeneration.set(generationId, current);
    }
    let nestedNumericOverlapCount = 0;
    for (const generationClaims of claimsByGeneration.values()) {
      for (const numeric of generationClaims.filter(
        (claim) => claim.claim_type === "numeric",
      )) {
        for (const broader of generationClaims) {
          if (broader.claim_id === numeric.claim_id) continue;
          if (
            Number(broader.source_span_start) <=
              Number(numeric.source_span_start) &&
            Number(broader.source_span_end) >= Number(numeric.source_span_end)
          ) {
            nestedNumericOverlapCount += 1;
          }
        }
      }
    }
    assert.equal(nestedNumericOverlapCount, 21);

    const attemptedFailures = failures
      .filter((failure) => failure.attempted === true)
      .map((failure) => ({
        case_id: failure.case_id,
        evidence_level: failure.evidence_level,
        failure_code: failure.failure_code,
      }));
    assert.deepEqual(attemptedFailures, [
      {
        case_id: "157248",
        evidence_level: "S3",
        failure_code: "RESPONSE_SCHEMA_INVALID",
      },
      {
        case_id: "156227",
        evidence_level: "S5",
        failure_code: "RESPONSE_NOT_JSON",
      },
    ]);
  },
);

test("selection policy JSON khớp loader hiện hành nhưng không chạy selection", () => {
  assert.doesNotThrow(() => assertFrozenSelectionPolicy());
  assert.equal(FROZEN_SELECTION_POLICY.policy_version, "selection_policy_v1");
  assert.equal(
    FROZEN_SELECTION_POLICY.status,
    "FROZEN_BEFORE_FINAL_VALIDATION",
  );
  assert.equal(FROZEN_SELECTION_POLICY.non_inferiority.margin, 0.03);
  assert.equal(FROZEN_SELECTION_POLICY.paired_bootstrap.iterations, 5000);
  assert.equal(FROZEN_SELECTION_POLICY.paired_bootstrap.confidence, 0.95);
  assert.equal(FROZEN_SELECTION_POLICY.paired_bootstrap.seed, 20260714);
});

test("compatibility wrappers trỏ tới active module", () => {
  const wrappers: Record<string, string> = {
    "batch/llm-narrative/run.ts": "research/llm/narrative/main",
    "batch/llm-narrative/aggregate.ts":
      "research/llm/narrative/aggregate-main",
    "batch/llm-validation/build-generation-index.ts":
      "research/llm/canonicalization/main",
    "batch/llm-validation/filter-deepseek-eval36.ts":
      "research/llm/canonicalization/filter-main",
    "batch/llm-validation/run-contract-validation.ts":
      "research/llm/contract_validation/main",
    "batch/llm-validation/run-claim-extraction.ts":
      "research/llm/claim_extraction/main",
    "ml/scripts/run_b_feature_engineering_layer.py":
      "research.ml.feature_engineering.main",
    "ml/scripts/run_e_preprocessing_layer.py":
      "research.ml.preprocessing.main",
    "ml/scripts/model_layer/run_f_model_training_layer.py":
      "research.ml.modeling.main",
    "ml/scripts/xai_layer/run_g_xai_evidence_layer.py":
      "research.ml.xai.main",
  };

  for (const [relativePath, target] of Object.entries(wrappers)) {
    const content = readFileSync(path.join(repositoryRoot, relativePath), "utf-8");
    assert.match(content, new RegExp(target.replaceAll(".", "\\."), "u"));
  }
});

test("unified dispatcher công bố đúng active stages", async () => {
  const result = await execFileAsync(
    process.execPath,
    ["--import", "tsx", "research/cli.ts", "--help"],
    { cwd: repositoryRoot },
  );
  const activeStages = [
    "ml:data-audit",
    "ml:target-audit",
    "ml:features",
    "ml:matrix",
    "ml:split",
    "ml:preprocess",
    "ml:train",
    "ml:xai",
    "ml:xai-quality",
    "ml:ir",
    "ml:evidence",
    "llm:generate",
    "llm:aggregate",
    "llm:filter-deepseek",
    "llm:canonicalize",
    "llm:contract",
    "llm:claims",
  ];

  for (const stage of activeStages) assert.match(result.stdout, new RegExp(stage, "u"));
  assert.doesNotMatch(result.stdout, /llm:selection/u);
});
