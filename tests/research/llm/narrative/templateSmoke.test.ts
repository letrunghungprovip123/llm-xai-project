import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  buildPrompt,
  getModelConfig,
  isGenerationUsable,
  runNarrativePipeline,
  type GenerationRecord,
} from "../../../../research/llm/narrative/index";
import {
  createEvidencePackage,
  createEvidencePackages,
  createTemplateRunOptions,
} from "./fixtures";

test("Template chạy đủ S0-S5 mà không gọi provider", async () => {
  const temporaryDir = await mkdtemp(path.join(os.tmpdir(), "narrative-r6-"));

  try {
    const inputPath = path.join(temporaryDir, "evidence_packages.jsonl");
    const outputDir = path.join(temporaryDir, "output");
    const packages = createEvidencePackages();
    const inputText = `${packages.map((item) => JSON.stringify(item)).join("\n")}\n`;
    await writeFile(inputPath, inputText, "utf-8");

    const result = await runNarrativePipeline(
      createTemplateRunOptions(inputPath, outputDir),
    );

    assert.equal(result.shard_count, 1);
    assert.equal(result.planned_generation_count, 6);
    assert.equal(result.completed_generation_count, 6);
    assert.equal(result.failed_generation_count, 0);

    const generationPath = path.join(
      result.shard_paths[0],
      "generations.jsonl",
    );
    const records = (await readFile(generationPath, "utf-8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line) as GenerationRecord);

    assert.equal(records.length, 6);
    assert.equal(records.every(isGenerationUsable), true);
    assert.deepEqual(
      new Set(records.map((record) => record.evidence_level)),
      new Set(["S0", "S1", "S2", "S3", "S4", "S5"]),
    );
    assert.equal(
      records.every((record) => record.model_id === "template_baseline"),
      true,
    );
    assert.equal(
      records.every((record) => record.runtime_metrics.provider_api_cost_usd === 0),
      true,
    );
  } finally {
    await rm(temporaryDir, { recursive: true, force: true });
  }
});

test("prompt ID và content hash ổn định cho cùng input", () => {
  const packageItem = createEvidencePackage("S5");
  const model = getModelConfig("template_baseline");

  const first = buildPrompt(packageItem, model, "prompt_v1");
  const second = buildPrompt(packageItem, model, "prompt_v1");

  assert.equal(first.prompt_id, second.prompt_id);
  assert.equal(first.message_sha256, second.message_sha256);
  assert.equal(
    first.message_sha256,
    "0b8fee51b45a86ad1562b14df21fe4ff28ab1e5e1bdf47036df24f289156dd81",
  );
  assert.equal(
    first.prompt_id,
    "prompt_3160044577e9483bb828ed6cd8887a84462eeb6246c331bbc959fc9441f966a9",
  );
  assert.equal(first.section_flags.has_backend_skeleton_section, true);
  assert.match(first.message_text, /BACKEND SKELETON/);
});
