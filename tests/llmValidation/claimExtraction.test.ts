import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import type { ClaimExtractionRawResponse } from "../../contracts/validation-claims";
import { postJsonWithRetry } from "../../research/llm/narrative/runners/httpHelpers";

import {
  ATOMIC_CLAIM_RESPONSE_JSON_SCHEMA,
  ClaimExtractionValidationError,
  parseNumericClaimValue,
  validateAndNormalizeClaimPayload,
} from "../../research/llm/claim_extraction/atomicClaimSchema";
import {
  DeepSeekAtomicClaimExtractor,
  parseClaimExtractionResponse,
} from "../../research/llm/claim_extraction/deepseekAtomicClaimExtractor";
import { runAtomicClaimExtraction } from "../../research/llm/claim_extraction/claimExtractionRunner";
import { buildGenerationTextDocument } from "../../research/llm/claim_extraction/generationTextAdapter";
import { canonicalRow } from "./fixtures";

function validClaim(sourceText: string): Record<string, unknown> {
  return {
    source_section: "factor_explanation",
    source_factor_id: "factor_1",
    source_text: sourceText,
    claim_type: "feature_direction",
    subject_type: "feature",
    feature_id: "feature_a",
    concept_id: "",
    direction: "increase_risk",
    magnitude: "not_applicable",
    certainty: "probabilistic",
    causal_strength: "associational",
    numeric_value_text: "",
    numeric_unit: "",
    numeric_role: "not_applicable",
    normalized_claim_key: " FEATURE_A | increase_risk ",
  };
}

function successfulRawResponse(rawText: string): ClaimExtractionRawResponse {
  return {
    raw_text: rawText,
    usage: { prompt_tokens: 17, completion_tokens: 8, total_tokens: 25 },
    stop_reason: "stop",
    response_received: true,
    provider_request_id: "chatcmpl_test",
    provider_returned_model_id: "deepseek-v4-flash",
    retry_count: 0,
    http_status: 200,
    api_error_type: null,
    api_error_message: null,
  };
}

test("provider schema does not ask the model for indices or source offsets", () => {
  const properties =
    ATOMIC_CLAIM_RESPONSE_JSON_SCHEMA.properties.claims.items.properties;
  assert.equal("local_claim_index" in properties, false);
  assert.equal("source_span_start" in properties, false);
  assert.equal("source_span_end" in properties, false);
});

test("claim payload receives a deterministic index and exact source span", () => {
  const document = buildGenerationTextDocument(canonicalRow());
  const sourceText = "Tín hiệu A góp phần làm tăng rủi ro dự đoán của mô hình.";
  const result = validateAndNormalizeClaimPayload(
    { claims: [validClaim(sourceText)] },
    document,
  );

  const claim = result.claims.find(
    (item) => item.claim_type === "feature_direction",
  );
  assert.ok((claim?.local_claim_index ?? 0) > 0);
  assert.equal(claim?.feature_id, "feature_a");
  assert.equal(claim?.magnitude, null);
  assert.equal(claim?.claim_origin, "llm");
  assert.equal(result.postprocess_metrics.llm_claim_count, 1);
  assert.equal(result.postprocess_metrics.deterministic_claim_count_added, 4);
  assert.equal(result.claims.length, 5);
  assert.deepEqual(
    result.claims.map((item) => item.local_claim_index),
    [1, 2, 3, 4, 5],
  );
  assert.equal(
    document.generation_text.slice(
      claim?.source_span_start,
      claim?.source_span_end,
    ),
    sourceText,
  );
});

test("model contribution wording is conservatively demoted to associational", () => {
  const document = buildGenerationTextDocument(canonicalRow());
  const sourceText = "Tín hiệu A góp phần làm tăng rủi ro dự đoán của mô hình.";
  const result = validateAndNormalizeClaimPayload(
    {
      claims: [
        {
          ...validClaim(sourceText),
          causal_strength: "causal",
        },
      ],
    },
    document,
  );

  const direction = result.claims.find(
    (claim) => claim.claim_type === "feature_direction",
  );
  assert.equal(direction?.causal_strength, "associational");
  assert.equal(result.postprocess_metrics.causal_overclaim_count_demoted, 1);
});

test("numeric parser accepts percent and common decimal/group separators", () => {
  assert.deepEqual(parseNumericClaimValue("91.92%", ""), {
    value: 91.92,
    unit: "percent",
  });
  assert.deepEqual(parseNumericClaimValue("91,92", "percent"), {
    value: 91.92,
    unit: "percent",
  });
  assert.deepEqual(parseNumericClaimValue("1,250", "count"), {
    value: 1250,
    unit: "count",
  });
});

test("numeric parser rejects a percent suffix with a conflicting unit", () => {
  assert.throws(
    () => parseNumericClaimValue("91.92%", "months"),
    (error: unknown) =>
      error instanceof ClaimExtractionValidationError &&
      error.code === "RESPONSE_SCHEMA_INVALID",
  );
});

test("postprocessor splits numeric attributes and keeps numeric roles separate", () => {
  const predictionSummary =
    "Mô hình dự đoán rủi ro cao 91.92%, vượt ngưỡng 50.00%.";
  const document = buildGenerationTextDocument(
    canonicalRow({
      parsedOutput: {
        prediction_summary: predictionSummary,
        factors: [],
        uncertainty_note: "Kết quả có độ không chắc chắn.",
        distributed_evidence_note: "",
        safe_summary: "Cần xem xét thêm thông tin.",
      },
    }),
  );
  const result = validateAndNormalizeClaimPayload(
    {
      claims: [
        {
          source_section: "prediction_summary",
          source_factor_id: "",
          source_text: predictionSummary,
          claim_type: "prediction",
          subject_type: "prediction",
          feature_id: "",
          concept_id: "",
          direction: "increase_risk",
          magnitude: "strong",
          certainty: "probabilistic",
          causal_strength: "none",
          numeric_value_text: "91.92%",
          numeric_unit: "percent",
          numeric_role: "prediction_score",
          normalized_claim_key: "prediction high risk 91.92 percent",
        },
        {
          source_section: "prediction_summary",
          source_factor_id: "",
          source_text: "vượt ngưỡng 50.00%",
          claim_type: "numeric",
          subject_type: "prediction",
          feature_id: "",
          concept_id: "",
          direction: "unknown",
          magnitude: "not_applicable",
          certainty: "probabilistic",
          causal_strength: "none",
          numeric_value_text: "50.00%",
          numeric_unit: "percent",
          numeric_role: "decision_threshold",
          normalized_claim_key: "decision threshold 50 percent",
        },
      ],
    },
    document,
  );

  const prediction = result.claims.find(
    (claim) => claim.claim_type === "prediction",
  );
  const numericClaims = result.claims.filter(
    (claim) => claim.claim_type === "numeric",
  );
  assert.equal(prediction?.numeric_value, null);
  assert.equal(prediction?.numeric_role, null);
  assert.equal(numericClaims.length, 2);
  assert.deepEqual(
    numericClaims.map((claim) => claim.numeric_role).sort(),
    ["decision_threshold", "prediction_score"],
  );
  assert.equal(
    numericClaims.find((claim) => claim.numeric_role === "prediction_score")
      ?.source_text,
    "91.92%",
  );
  assert.equal(
    numericClaims.find((claim) => claim.numeric_role === "decision_threshold")
      ?.source_text,
    "50.00%",
  );
  assert.equal(result.postprocess_metrics.derived_numeric_claim_count_added, 1);
});

test("semantic dedup keeps prediction_summary and marks safe_summary redundant", () => {
  const prediction = "Mô hình dự đoán rủi ro cao.";
  const safeSummary = "Dựa trên phân tích, mô hình dự đoán rủi ro cao.";
  const document = buildGenerationTextDocument(
    canonicalRow({
      parsedOutput: {
        prediction_summary: prediction,
        factors: [],
        uncertainty_note: "Kết quả có độ không chắc chắn.",
        distributed_evidence_note: "",
        safe_summary: safeSummary,
      },
    }),
  );
  const common = {
    source_factor_id: "",
    claim_type: "prediction",
    subject_type: "prediction",
    feature_id: "",
    concept_id: "",
    direction: "increase_risk",
    magnitude: "strong",
    certainty: "probabilistic",
    causal_strength: "none",
    numeric_value_text: "",
    numeric_unit: "",
    numeric_role: "not_applicable",
  };
  const result = validateAndNormalizeClaimPayload(
    {
      claims: [
        {
          ...common,
          source_section: "safe_summary",
          source_text: safeSummary,
          normalized_claim_key: "safe summary prediction",
        },
        {
          ...common,
          source_section: "prediction_summary",
          source_text: prediction,
          normalized_claim_key: "main prediction",
        },
      ],
    },
    document,
  );

  const predictions = result.claims.filter(
    (claim) => claim.claim_type === "prediction",
  );
  assert.equal(predictions.length, 1);
  assert.equal(predictions[0]?.source_section, "prediction_summary");
  assert.equal(result.postprocess_metrics.semantic_duplicate_count_removed, 1);
  assert.deepEqual(
    result.postprocess_metrics.semantically_redundant_source_slots,
    ["safe_summary"],
  );
});

test("DeepSeek parser accepts a fenced JSON object", () => {
  const document = buildGenerationTextDocument(canonicalRow());
  const sourceText = "Tín hiệu A góp phần làm tăng rủi ro dự đoán của mô hình.";
  const payload = parseClaimExtractionResponse(
    `\`\`\`json\n${JSON.stringify({ claims: [validClaim(sourceText)] })}\n\`\`\``,
    document,
  );
  assert.equal(payload.postprocess_metrics.llm_claim_count, 1);
});

test("DeepSeek extractor reuses the 720-generation API contract", async () => {
  const originalFetch = globalThis.fetch;
  const originalApiKey = process.env.DEEPSEEK_API_KEY;
  let requestedUrl = "";
  let requestedBody: Record<string, unknown> = {};

  process.env.DEEPSEEK_API_KEY = "test-key";
  globalThis.fetch = async (input, init) => {
    requestedUrl = String(input);
    requestedBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
    return new Response(
      JSON.stringify({
        id: "chatcmpl_deepseek_test",
        model: "deepseek-v4-flash",
        choices: [
          {
            finish_reason: "stop",
            message: { content: '{"claims":[]}' },
          },
        ],
        usage: { prompt_tokens: 100, completion_tokens: 10, total_tokens: 110 },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  };

  try {
    const extractor = new DeepSeekAtomicClaimExtractor({
      baseUrl: "https://api.deepseek.com",
      apiKeyEnv: "DEEPSEEK_API_KEY",
      modelId: "deepseek-v4-flash",
      maxTokens: 3000,
      temperature: 0,
      topP: 1,
      timeoutMs: 1000,
      maxRetries: 0,
      retryDelayMs: 1,
      inputCostPerMillion: null,
      outputCostPerMillion: null,
    });
    const raw = await extractor.extractRaw(
      buildGenerationTextDocument(canonicalRow()),
    );

    assert.equal(requestedUrl, "https://api.deepseek.com/chat/completions");
    assert.equal(requestedBody.model, "deepseek-v4-flash");
    assert.deepEqual(requestedBody.response_format, { type: "json_object" });
    assert.deepEqual(requestedBody.thinking, { type: "disabled" });
    assert.equal(requestedBody.temperature, 0);
    assert.equal(requestedBody.top_p, 1);
    assert.equal(Array.isArray(requestedBody.messages), true);
    assert.equal(raw.provider_request_id, "chatcmpl_deepseek_test");
    assert.equal(raw.provider_returned_model_id, "deepseek-v4-flash");
    assert.equal(raw.http_status, 200);
    assert.equal(raw.retry_count, 0);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalApiKey === undefined) delete process.env.DEEPSEEK_API_KEY;
    else process.env.DEEPSEEK_API_KEY = originalApiKey;
  }
});

test("HTTP helper reports the actual retry count for a non-retryable error", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response('{"error":{"message":"bad request"}}', {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });

  try {
    const result = await postJsonWithRetry({
      url: "https://example.invalid/chat/completions",
      headers: { "Content-Type": "application/json" },
      body: {},
      timeout_ms: 1000,
      max_retries: 3,
      retry_delay_ms: 0,
    });
    assert.equal(result.ok, false);
    assert.equal(result.status_code, 400);
    assert.equal(result.retry_count, 0);
    assert.equal(result.error_type, "HTTP_400");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("claim extraction rejects source text outside the declared section", () => {
  const document = buildGenerationTextDocument(canonicalRow());
  assert.throws(
    () =>
      validateAndNormalizeClaimPayload(
        {
          claims: [
            {
              ...validClaim("Mô hình dự đoán mức rủi ro cao."),
              source_section: "factor_explanation",
            },
          ],
        },
        document,
      ),
    (error: unknown) =>
      error instanceof ClaimExtractionValidationError &&
      error.code === "SOURCE_SPAN_INVALID",
  );
});

test("runner audits a failed response, retries it and then reuses success", async (context) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "claim-extraction-"));
  context.after(async () => rm(directory, { recursive: true, force: true }));

  const generationIndexPath = path.join(directory, "generation_index.jsonl");
  const claimsOutputPath = path.join(directory, "claims.jsonl");
  const failuresOutputPath = path.join(directory, "claim_extraction_failures.jsonl");
  const attemptsOutputPath = path.join(directory, "claim_extraction_attempts.jsonl");
  await writeFile(
    generationIndexPath,
    `${JSON.stringify(canonicalRow())}\n`,
    "utf8",
  );

  const exactSource = "Tín hiệu A góp phần làm tăng rủi ro dự đoán của mô hình.";
  let shouldReturnValidSource = false;
  let callCount = 0;
  const extractor = {
    getConfig: () => ({
      modelId: "deepseek-v4-flash",
      inputCostPerMillion: null,
      outputCostPerMillion: null,
    }),
    extractRaw: async () => {
      callCount += 1;
      return successfulRawResponse(
        JSON.stringify({
          claims: [
            validClaim(
              shouldReturnValidSource ? exactSource : "đoạn không có trong nguồn",
            ),
          ],
        }),
      );
    },
  };
  const options = {
    generationIndexPath,
    claimsOutputPath,
    failuresOutputPath,
    attemptsOutputPath,
    limit: null,
    force: false,
    checkpointEvery: 1,
  };

  const failed = await runAtomicClaimExtraction(options, extractor);
  assert.equal(failed.successful_generations, 0);
  assert.equal(failed.new_provider_calls, 1);
  assert.deepEqual(failed.usage_for_new_calls, {
    input_tokens: 17,
    output_tokens: 8,
    total_tokens: 25,
  });

  const firstAttempts = await readJsonl(attemptsOutputPath);
  assert.equal(firstAttempts[0]?.status, "VALIDATION_FAILED");
  assert.equal(firstAttempts[0]?.failure_code, "SOURCE_SPAN_INVALID");
  assert.equal(firstAttempts[0]?.attempt_schema_version, "claim_extraction_attempt_v2");
  assert.equal(firstAttempts[0]?.extractor_provider, "deepseek");
  assert.equal(firstAttempts[0]?.provider_request_id, "chatcmpl_test");
  assert.equal(firstAttempts[0]?.http_status, 200);
  assert.equal(firstAttempts[0]?.raw_response_text, null);
  assert.match(String(firstAttempts[0]?.raw_response_sha256), /^[a-f0-9]{64}$/u);
  assert.deepEqual(firstAttempts[0]?.usage, {
    input_tokens: 17,
    output_tokens: 8,
    total_tokens: 25,
  });

  shouldReturnValidSource = true;
  const recovered = await runAtomicClaimExtraction(options, extractor);
  assert.equal(recovered.successful_generations, 1);
  assert.equal(recovered.failed_or_unusable_generations, 0);
  assert.equal(recovered.total_claims, 5);
  assert.equal(recovered.postprocess_for_new_successes.llm_claims_received, 1);
  assert.equal(recovered.postprocess_for_new_successes.deterministic_claims_added, 4);

  const attemptsAfterRetry = await readJsonl(attemptsOutputPath);
  assert.equal(attemptsAfterRetry.length, 2);
  assert.equal(attemptsAfterRetry[1]?.attempt_number, 2);
  assert.equal(attemptsAfterRetry[1]?.status, "SUCCESS");
  assert.match(
    String(attemptsAfterRetry[1]?.extractor_prompt_sha256),
    /^[a-f0-9]{64}$/u,
  );
  const writtenClaims = await readJsonl(claimsOutputPath);
  assert.ok(
    writtenClaims.every((claim) =>
      /^[a-f0-9]{64}$/u.test(String(claim.extractor_prompt_sha256))),
  );
  assert.equal((await readFile(failuresOutputPath, "utf8")).trim(), "");

  const reused = await runAtomicClaimExtraction(options, extractor);
  assert.equal(reused.reused_successes, 1);
  assert.equal(reused.new_provider_calls, 0);
  assert.equal(callCount, 2);
  assert.equal((await readJsonl(attemptsOutputPath)).length, 2);
});

test("runner keeps v1 audit history and continues its attempt number", async (context) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "claim-v1-resume-"));
  context.after(async () => rm(directory, { recursive: true, force: true }));

  const row = canonicalRow();
  const generationIndexPath = path.join(directory, "generation_index.jsonl");
  const claimsOutputPath = path.join(directory, "claims.jsonl");
  const failuresOutputPath = path.join(directory, "failures.jsonl");
  const attemptsOutputPath = path.join(directory, "attempts.jsonl");
  await writeFile(generationIndexPath, `${JSON.stringify(row)}\n`, "utf8");
  await writeFile(
    attemptsOutputPath,
    `${JSON.stringify({
      attempt_schema_version: "claim_extraction_attempt_v1",
      attempt_id: "claim_attempt_legacy",
      generation_id: row.generation_id,
      canonical_key: row.canonical_key,
      source_ir_id: row.source_ir_id,
      case_id: row.case_id,
      evidence_level: row.evidence_level,
      repeat_id: row.repeat_id,
      attempt_number: 1,
      started_at: "2026-01-01T00:00:00.000Z",
      completed_at: "2026-01-01T00:00:01.000Z",
      duration_ms: 1000,
      status: "BEDROCK_FAILED",
      failure_code: "BEDROCK_CALL_FAILED",
      failure_message: "Historical smoke failure.",
      result_claim_count: 0,
      source_input_sha256: "a".repeat(64),
      extractor_provider: "amazon_bedrock",
      extractor_model_id: "test-haiku",
      extractor_version: "atomic_claim_extractor_v2.0.0",
      extractor_prompt_version: "atomic_claim_extraction_prompt_v2",
      response_received: false,
      raw_response_sha256: null,
      raw_response_text: null,
      stop_reason: null,
      usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
    })}\n`,
    "utf8",
  );

  const sourceText = "Tín hiệu A góp phần làm tăng rủi ro dự đoán của mô hình.";
  const extractor = {
    getConfig: () => ({ modelId: "deepseek-v4-flash" }),
    extractRaw: async () =>
      successfulRawResponse(
        JSON.stringify({ claims: [validClaim(sourceText)] }),
      ),
  };

  const summary = await runAtomicClaimExtraction(
    {
      generationIndexPath,
      claimsOutputPath,
      failuresOutputPath,
      attemptsOutputPath,
      limit: null,
      force: false,
      checkpointEvery: 1,
    },
    extractor,
  );

  assert.equal(summary.successful_generations, 1);
  const attempts = await readJsonl(attemptsOutputPath);
  assert.equal(attempts.length, 2);
  assert.equal(attempts[0]?.attempt_schema_version, "claim_extraction_attempt_v1");
  assert.equal(attempts[1]?.attempt_schema_version, "claim_extraction_attempt_v2");
  assert.equal(attempts[1]?.attempt_number, 2);
});

test("runner preserves DeepSeek provider errors in attempts and failures", async (context) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "claim-provider-error-"));
  context.after(async () => rm(directory, { recursive: true, force: true }));

  const generationIndexPath = path.join(directory, "generation_index.jsonl");
  const claimsOutputPath = path.join(directory, "claims.jsonl");
  const failuresOutputPath = path.join(directory, "failures.jsonl");
  const attemptsOutputPath = path.join(directory, "attempts.jsonl");
  await writeFile(
    generationIndexPath,
    `${JSON.stringify(canonicalRow())}\n`,
    "utf8",
  );

  const extractor = {
    getConfig: () => ({ modelId: "deepseek-v4-flash" }),
    extractRaw: async () => ({
      raw_text: '{"error":"rate limit"}',
      usage: null,
      stop_reason: null,
      response_received: true,
      provider_request_id: "request_rate_limited",
      provider_returned_model_id: null,
      retry_count: 3,
      http_status: 429,
      api_error_type: "HTTP_429",
      api_error_message: "DeepSeek rate limit exceeded.",
    }),
  };

  const summary = await runAtomicClaimExtraction(
    {
      generationIndexPath,
      claimsOutputPath,
      failuresOutputPath,
      attemptsOutputPath,
      limit: null,
      force: false,
      checkpointEvery: 1,
    },
    extractor,
  );

  assert.equal(summary.successful_generations, 0);
  assert.equal(summary.failed_or_unusable_generations, 1);
  assert.equal(summary.new_provider_calls, 1);

  const attempts = await readJsonl(attemptsOutputPath);
  assert.equal(attempts[0]?.status, "PROVIDER_FAILED");
  assert.equal(attempts[0]?.failure_code, "PROVIDER_CALL_FAILED");
  assert.equal(attempts[0]?.response_received, true);
  assert.equal(attempts[0]?.retry_count, 3);
  assert.equal(attempts[0]?.http_status, 429);
  assert.equal(attempts[0]?.provider_request_id, "request_rate_limited");
  assert.match(String(attempts[0]?.raw_response_sha256), /^[a-f0-9]{64}$/u);

  const failures = await readJsonl(failuresOutputPath);
  assert.equal(failures[0]?.failure_schema_version, "claim_extraction_failure_v2");
  assert.equal(failures[0]?.failure_code, "PROVIDER_CALL_FAILED");
  assert.equal(failures[0]?.extractor_provider, "deepseek");
  assert.match(String(failures[0]?.extractor_prompt_sha256), /^[a-f0-9]{64}$/u);
});

async function readJsonl(filePath: string): Promise<Record<string, unknown>[]> {
  const text = await readFile(filePath, "utf8");
  return text
    .split(/\r?\n/u)
    .filter(Boolean)
    .map((line) => JSON.parse(line) as Record<string, unknown>);
}
