import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

import {
  validateAndNormalizeClaimPayload,
} from "../../../research/ts/claim_extraction/index";
import type {
  GenerationTextDocument,
} from "../../../research/ts/claim_extraction/index";
import {
  FROZEN_SELECTION_POLICY,
  assertFrozenSelectionPolicy,
} from "../../../research/ts/selection/index";
import {
  DEFAULT_CLAIMS_INPUT_PATH,
  DEFAULT_EVIDENCE_PACKAGES_PATH,
  DEFAULT_GENERATION_INDEX_PATH,
  loadValidationInputs,
} from "../../../research/ts/claim_validation/input";

const execFileAsync = promisify(execFile);
const repositoryRoot = process.cwd();
const configuredGoldenRoot = process.env.RESEARCH_GOLDEN_ROOT;
const goldenRoot = configuredGoldenRoot
  ? path.resolve(configuredGoldenRoot)
  : repositoryRoot;
const validationGoldenMode =
  process.env.VALIDATION_GOLDEN_MODE ?? "config-only";
if (!["config-only", "required"].includes(validationGoldenMode)) {
  throw new Error(
    `Unsupported VALIDATION_GOLDEN_MODE: ${validationGoldenMode}`,
  );
}
const requiredGoldenMode = validationGoldenMode === "required";

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

test("canonical validation inputs are direct and strict-valid", async (context) => {
  if (!requiredGoldenMode) {
    context.diagnostic(
      "CONFIG_ONLY: canonical paths are checked without reading artifact bytes.",
    );
    assert.equal(DEFAULT_CLAIMS_INPUT_PATH.includes("claims_final.jsonl"), true);
    assert.equal(DEFAULT_GENERATION_INDEX_PATH.includes("generation_index.jsonl"), true);
    assert.equal(DEFAULT_EVIDENCE_PACKAGES_PATH.includes("evidence_packages_36.jsonl"), true);
    return;
  }
  const loaded = await loadValidationInputs({ repositoryRoot: goldenRoot });
  assert.equal(loaded.claims.length, 14680);
  assert.equal(loaded.generations.length, 648);
  assert.equal(loaded.evidencePackages.length, 216);
});

test(
  "golden canonical matrix giữ 648/638/10 và 10 truncated S4",
  { skip: !requiredGoldenMode },
  () => {
    const rows = readJsonl(
      "data/reports/llm_validation/validation_v1/canonicalization/generation_index.jsonl",
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
    assert.equal(
      rows.every(
        (row) =>
          row.matrix_role === "main" &&
          row.is_baseline === false &&
          row.eligible_for_selection === true,
      ),
      true,
    );
    const templateBaseline = readJsonl(
      "data/reports/llm_validation/validation_v1/canonicalization/template_baseline_index.jsonl",
    );
    assert.equal(templateBaseline.length, 216);
    assert.equal(
      templateBaseline.every(
        (row) =>
          row.matrix_role === "baseline" &&
          row.is_baseline === true &&
          row.eligible_for_selection === false &&
          row.model_id === "template_baseline",
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
  { skip: !requiredGoldenMode },
  () => {
    const rows = readJsonl(
      "data/reports/llm_validation/validation_v1/canonicalization/generation_index.jsonl",
    );
    const evidence = readJsonl(
      "data/reports/llm_validation/validation_v1/canonicalization/evidence_packages_36.jsonl",
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
  { skip: !requiredGoldenMode },
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
  "claim v2.1 giữ full promoted cohort, không dùng smoke 21/383",
  { skip: !requiredGoldenMode },
  () => {
    const base =
      "data/reports/llm_validation/validation_v1/claim_extraction_deepseek_v2_1";
    const attempts = readJsonl(`${base}/claim_extraction_attempts.jsonl`);
    const claims = readJsonl(`${base}/claims.jsonl`);
    const failures = readJsonl(`${base}/claim_extraction_failures.jsonl`);

    assert.equal(attempts.length, 680);
    assert.equal(attempts.filter((item) => item.status === "SUCCESS").length, 595);
    assert.equal(
      attempts.filter((item) => item.status === "VALIDATION_FAILED").length,
      76,
    );
    assert.equal(
      attempts.filter((item) => item.status === "PROVIDER_FAILED").length,
      9,
    );
    assert.equal(claims.length, 14640);
    assert.equal(new Set(claims.map((claim) => claim.claim_id)).size, 14640);
    assert.equal(new Set(claims.map((claim) => claim.generation_id)).size, 638);
    assert.equal(failures.length, 10);
    assert.equal(
      failures.every(
        (failure) =>
          failure.attempted === false &&
          failure.failure_code === "GENERATION_UNUSABLE",
      ),
      true,
    );
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

test("unified dispatcher công bố đúng active stages", async () => {
  const result = await execFileAsync(
    process.execPath,
    ["--import", "tsx", "research/ts/cli.ts", "--help"],
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
    "ml:model-ready-audit",
    "ml:xai",
    "ml:xai-quality",
    "ml:ir",
    "ml:evidence",
    "ml:evidence-subset",
    "llm:generate",
    "llm:aggregate",
    "llm:filter-deepseek",
    "llm:canonicalize",
    "llm:contract",
    "llm:claims",
    "llm:claims-finalize",
  ];

  for (const stage of activeStages) assert.match(result.stdout, new RegExp(stage, "u"));
  assert.doesNotMatch(result.stdout, /llm:selection/u);
});


test("provider payload canonicalization chuẩn hóa numeric role và exact source", () => {
  const sourceText = "Dự đoán rủi ro tín dụng là thấp với xác suất 0.23.";
  const label = "[prediction_summary]\n";
  const generationText = `${label}${sourceText}\n\n`;
  const document: GenerationTextDocument = {
    generation_text: generationText,
    source_input_sha256: "test-source",
    section_spans: [{
      source_section: "prediction_summary",
      source_factor_id: null,
      start: label.length,
      end: label.length + sourceText.length,
    }],
    factor_metadata: [],
  };

  const payload = validateAndNormalizeClaimPayload({
    claims: [{
      source_section: "prediction_summary",
      source_factor_id: "",
      source_text: "Rủi ro thấp với xác suất 0.23.",
      claim_type: "prediction",
      subject_type: "prediction",
      feature_id: "",
      concept_id: "",
      direction: "unknown",
      magnitude: "unknown",
      certainty: "probabilistic",
      causal_strength: "none",
      numeric_value_text: "0.23",
      numeric_unit: "",
      numeric_role: "not_applicable",
      normalized_claim_key: "low risk prediction",
    }],
  }, document);

  const prediction = payload.claims.find(
    (claim) => claim.claim_type === "prediction",
  );
  const numeric = payload.claims.find(
    (claim) => claim.claim_type === "numeric",
  );
  if (!prediction || !numeric) {
    throw new Error("Expected prediction and numeric claims.");
  }
  assert.equal(prediction.direction, "decrease_risk");
  assert.equal(prediction.source_text, sourceText);
  assert.equal(numeric.numeric_role, "prediction_score");
  assert.equal(numeric.source_text, "0.23");
});

test("aggregate directional claim không có declared ID được canonicalize", () => {
  const sourceText = "Dự đoán dựa trên nhiều nhóm bằng chứng.";
  const label = "[safe_summary]\n";
  const document: GenerationTextDocument = {
    generation_text: `${label}${sourceText}\n\n`,
    source_input_sha256: "test-source",
    section_spans: [{
      source_section: "safe_summary",
      source_factor_id: null,
      start: label.length,
      end: label.length + sourceText.length,
    }],
    factor_metadata: [],
  };

  const payload = validateAndNormalizeClaimPayload({
    claims: [{
      source_section: "safe_summary",
      source_factor_id: "",
      source_text: sourceText,
      claim_type: "concept_direction",
      subject_type: "concept",
      feature_id: "",
      concept_id: "undeclared_concept",
      direction: "increase_risk",
      magnitude: "unknown",
      certainty: "hedged",
      causal_strength: "associational",
      numeric_value_text: "",
      numeric_unit: "",
      numeric_role: "not_applicable",
      normalized_claim_key: "distributed evidence",
    }],
  }, document);

  assert.equal(payload.claims[0]?.claim_type, "distributed_evidence");
  assert.equal(payload.claims[0]?.subject_type, "evidence");
  assert.equal(payload.claims[0]?.concept_id, null);
});

test("deterministic presence dùng đúng repeated factor occurrence", () => {
  const firstText = "Hồ sơ thứ nhất";
  const secondText = "Hồ sơ thứ hai";
  const firstLabel = "[factor_name:application_profile]\n";
  const separator = "\n\n";
  const secondLabel = "[factor_name:application_profile]\n";
  const firstStart = firstLabel.length;
  const secondStart =
    firstLabel.length + firstText.length + separator.length + secondLabel.length;
  const document: GenerationTextDocument = {
    generation_text:
      `${firstLabel}${firstText}${separator}${secondLabel}${secondText}${separator}`,
    source_input_sha256: "test-source",
    section_spans: [
      {
        source_section: "factor_name",
        source_factor_id: "application_profile",
        start: firstStart,
        end: firstStart + firstText.length,
      },
      {
        source_section: "factor_name",
        source_factor_id: "application_profile",
        start: secondStart,
        end: secondStart + secondText.length,
      },
    ],
    factor_metadata: [
      {
        source_factor_id: "application_profile",
        declared_feature_ids: ["FEATURE_FIRST"],
        declared_concept_ids: [],
      },
      {
        source_factor_id: "application_profile",
        declared_feature_ids: ["FEATURE_SECOND"],
        declared_concept_ids: [],
      },
    ],
  };

  const payload = validateAndNormalizeClaimPayload({ claims: [] }, document);
  const second = payload.claims.find(
    (claim) => claim.feature_id === "FEATURE_SECOND",
  );
  if (!second) throw new Error("Expected second presence claim.");
  assert.equal(second.source_text, secondText);
  assert.equal(second.source_span_start, secondStart);
});
