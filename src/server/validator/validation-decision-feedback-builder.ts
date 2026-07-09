// src/server/validator/validation-decision-feedback-builder.ts

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

/**
 * Batch J.3 - Validation Decision & Feedback Builder
 *
 * Purpose:
 * - Read Batch J.2 faithfulness validation outputs.
 * - Decide whether each explanation can be accepted or must be regenerated.
 * - Build regeneration feedback for Batch I when validation fails.
 *
 * Important:
 * - This file does NOT call DeepSeek.
 * - This file does NOT call Bedrock.
 * - This file does NOT implement an auto-loop.
 * - It only converts J.2 validation results into deterministic decision/feedback artifacts.
 *
 * Generality:
 * - It does not hard-code a specific failure such as "Loại thu nhập".
 * - It maps arbitrary J.2 rule/check failures into reusable repair instructions.
 * - Unknown future J.2 failures still produce safe generic feedback.
 */

export type J3RunMode = "evaluation" | "inference";
export type J3GeneratorType = "llm_api" | "template" | string;

export type J3DecisionStatus =
  | "ACCEPTED"
  | "ACCEPTED_WITH_WARNINGS"
  | "NEEDS_REGENERATION"
  | "SYSTEM_ERROR";

export type J3NextAction =
  | "FINALIZE"
  | "FINALIZE_WITH_WARNINGS"
  | "REGENERATE_BATCH_I"
  | "REVIEW_PIPELINE_ERROR";

export type J3FailureType =
  | "prediction_value_mismatch"
  | "direction_mismatch"
  | "ungrounded_feature"
  | "ambiguous_feature_reference"
  | "unsupported_concept"
  | "missing_required_limitation"
  | "schema_or_format_issue"
  | "unknown";

export type J3IssueSeverity = "warning" | "error";

export type J3FeedbackIssue = {
  claim_id?: string;
  claim_type?: string;
  section?: string;
  claim_text: string;
  failure_type: J3FailureType;
  validator_rule_id?: string;
  severity: J3IssueSeverity;
  reason: string;
  repair_instruction: string;
  evidence?: Record<string, unknown>;
};

export type J3RegenerationFeedback = {
  feedback_id: string;
  created_at: string;
  ir_id: string;
  explanation_id?: string;
  validation_id?: string;
  attempt: number;
  source_batch: "Batch J.3";
  status: "FAIL" | "PASS_WITH_WARN";
  summary: {
    total_issues: number;
    error_count: number;
    warning_count: number;
  };
  issues: J3FeedbackIssue[];
  global_repair_instructions: string[];
};

export type J3ValidationDecision = {
  decision_id: string;
  created_at: string;
  ir_id: string;
  explanation_id?: string;
  validation_id?: string;
  customer_id?: string;
  source_validation_status: string;
  decision_status: J3DecisionStatus;
  next_action: J3NextAction;
  feedback_required: boolean;
  can_show_to_user: boolean;
  recommended_fallback: "none" | "template_explanation" | "human_review";
  issue_summary: {
    total_issues: number;
    error_count: number;
    warning_count: number;
    failed_claim_count: number;
    warning_claim_count: number;
  };
  feedback_id?: string;
  notes: string[];
};

export type J3FinalizationCandidate = {
  decision_id: string;
  ir_id: string;
  explanation_id?: string;
  validation_id?: string;
  customer_id?: string;
  decision_status: Extract<
    J3DecisionStatus,
    "ACCEPTED" | "ACCEPTED_WITH_WARNINGS"
  >;
  next_action: Extract<J3NextAction, "FINALIZE" | "FINALIZE_WITH_WARNINGS">;
  can_show_to_user: true;
  notes: string[];
};

export type J3Paths = {
  outputDir: string;
  validationJsonlPath: string;
  validationSummaryJsonPath: string;
  validationFailuresJsonPath: string;
  validationDecisionsJsonlPath: string;
  regenerationFeedbackJsonlPath: string;
  regenerationFeedbackSummaryJsonPath: string;
  finalizationCandidatesJsonlPath: string;
  validationDecisionReportMdPath: string;
};

export type RunJ3Options = {
  projectRoot?: string;
  runMode?: J3RunMode;
  generatorType?: J3GeneratorType;
  validationDir?: string;
  validationJsonlPath?: string;
  validationSummaryJsonPath?: string;
  validationFailuresJsonPath?: string;

  /**
   * If true, WARN-only records can also produce feedback.
   * Default false to avoid unnecessary Batch I regeneration and token cost.
   */
  generateFeedbackForWarnings?: boolean;

  /**
   * Regeneration attempt number assigned to feedback.
   * Default 1.
   */
  nextAttempt?: number;
};

export type RunJ3Result = {
  paths: J3Paths;
  decisions: J3ValidationDecision[];
  regenerationFeedback: J3RegenerationFeedback[];
  finalizationCandidates: J3FinalizationCandidate[];
  summary: J3Summary;
};

export type J3Summary = {
  report_name: string;
  created_at: string;
  batch: "Batch J.3";
  batch_version: "v1.0";
  mode: "validation_decision_and_feedback_builder";
  run_mode: J3RunMode;
  generator_type: J3GeneratorType;
  input_paths: {
    validation_jsonl_path: string;
    validation_summary_json_path: string;
    validation_failures_json_path: string;
  };
  output_paths: {
    validation_decisions_jsonl_path: string;
    regeneration_feedback_jsonl_path: string;
    regeneration_feedback_summary_json_path: string;
    finalization_candidates_jsonl_path: string;
    validation_decision_report_md_path: string;
  };
  counts: {
    validation_records: number;
    accepted_records: number;
    accepted_with_warnings_records: number;
    needs_regeneration_records: number;
    system_error_records: number;
    regeneration_feedback_records: number;
    finalization_candidate_records: number;
    total_feedback_issues: number;
    total_feedback_errors: number;
    total_feedback_warnings: number;
  };
  policy: {
    generate_feedback_for_warnings: boolean;
    next_attempt: number;
    auto_loop_enabled: false;
    calls_llm: false;
    calls_bedrock: false;
  };
};

type UnknownRecord = Record<string, unknown>;

type NormalizedClaim = {
  claim_id?: string;
  claim_type?: string;
  section?: string;
  text: string;
  status: string;
  checks: NormalizedCheck[];
  matched_features: unknown[];
  raw: UnknownRecord;
};

type NormalizedCheck = {
  rule_id?: string;
  status: string;
  severity?: string;
  message: string;
  evidence?: Record<string, unknown>;
  raw: UnknownRecord;
};

export async function runValidationDecisionFeedbackBuilder(
  options: RunJ3Options = {},
): Promise<RunJ3Result> {
  const runMode = options.runMode ?? "evaluation";
  const generatorType = options.generatorType ?? "llm_api";
  const generateFeedbackForWarnings =
    options.generateFeedbackForWarnings ?? false;
  const nextAttempt = options.nextAttempt ?? 1;

  const paths = buildJ3Paths({
    projectRoot: options.projectRoot ?? process.cwd(),
    runMode,
    generatorType,
    validationDir: options.validationDir,
    validationJsonlPath: options.validationJsonlPath,
    validationSummaryJsonPath: options.validationSummaryJsonPath,
    validationFailuresJsonPath: options.validationFailuresJsonPath,
  });

  const validationRecords = await readJsonlFile<UnknownRecord>(
    paths.validationJsonlPath,
  );

  const createdAt = new Date().toISOString();

  const decisions: J3ValidationDecision[] = [];
  const regenerationFeedback: J3RegenerationFeedback[] = [];
  const finalizationCandidates: J3FinalizationCandidate[] = [];

  for (const record of validationRecords) {
    const decision = buildDecisionForValidationRecord(record, {
      createdAt,
      generateFeedbackForWarnings,
    });

    decisions.push(decision);

    if (decision.decision_status === "NEEDS_REGENERATION") {
      const feedback = buildRegenerationFeedback(record, decision, {
        createdAt,
        nextAttempt,
      });

      regenerationFeedback.push(feedback);
      decision.feedback_id = feedback.feedback_id;
    }

    if (
      decision.decision_status === "ACCEPTED" ||
      decision.decision_status === "ACCEPTED_WITH_WARNINGS"
    ) {
      finalizationCandidates.push({
        decision_id: decision.decision_id,
        ir_id: decision.ir_id,
        explanation_id: decision.explanation_id,
        validation_id: decision.validation_id,
        customer_id: decision.customer_id,
        decision_status: decision.decision_status,
        next_action:
          decision.decision_status === "ACCEPTED"
            ? "FINALIZE"
            : "FINALIZE_WITH_WARNINGS",
        can_show_to_user: true,
        notes: decision.notes,
      });
    }
  }

  const summary = buildSummary({
    createdAt,
    runMode,
    generatorType,
    paths,
    validationRecords,
    decisions,
    regenerationFeedback,
    finalizationCandidates,
    generateFeedbackForWarnings,
    nextAttempt,
  });

  await writeArtifacts({
    paths,
    decisions,
    regenerationFeedback,
    finalizationCandidates,
    summary,
  });

  return {
    paths,
    decisions,
    regenerationFeedback,
    finalizationCandidates,
    summary,
  };
}

export function buildJ3Paths(input: {
  projectRoot: string;
  runMode: J3RunMode;
  generatorType: J3GeneratorType;
  validationDir?: string;
  validationJsonlPath?: string;
  validationSummaryJsonPath?: string;
  validationFailuresJsonPath?: string;
}): J3Paths {
  const outputDir =
    input.validationDir ??
    path.join(
      input.projectRoot,
      "data",
      "reports",
      "faithfulness_validation",
      input.runMode,
      input.generatorType,
    );

  return {
    outputDir,
    validationJsonlPath:
      input.validationJsonlPath ??
      path.join(outputDir, "faithfulness_validation.jsonl"),
    validationSummaryJsonPath:
      input.validationSummaryJsonPath ??
      path.join(outputDir, "faithfulness_validation_summary.json"),
    validationFailuresJsonPath:
      input.validationFailuresJsonPath ??
      path.join(outputDir, "faithfulness_validation_failures.json"),
    validationDecisionsJsonlPath: path.join(
      outputDir,
      "validation_decisions.jsonl",
    ),
    regenerationFeedbackJsonlPath: path.join(
      outputDir,
      "regeneration_feedback.jsonl",
    ),
    regenerationFeedbackSummaryJsonPath: path.join(
      outputDir,
      "regeneration_feedback_summary.json",
    ),
    finalizationCandidatesJsonlPath: path.join(
      outputDir,
      "finalization_candidates.jsonl",
    ),
    validationDecisionReportMdPath: path.join(
      outputDir,
      "validation_decision_report.md",
    ),
  };
}

function buildDecisionForValidationRecord(
  record: UnknownRecord,
  options: {
    createdAt: string;
    generateFeedbackForWarnings: boolean;
  },
): J3ValidationDecision {
  const irId = getIrId(record);
  const explanationId = getExplanationId(record);
  const validationId = getValidationId(record);
  const customerId = getCustomerIdFromValidation(record);
  const sourceStatus = getValidationStatus(record);

  const claims = extractClaimValidations(record);
  const issues = collectFeedbackIssues(record, {
    includeWarnings:
      options.generateFeedbackForWarnings || isFailStatus(sourceStatus),
  });

  const errorIssues = issues.filter((issue) => issue.severity === "error");
  const warningIssues = issues.filter((issue) => issue.severity === "warning");

  const failedClaimCount = claims.filter((claim) =>
    isFailStatus(claim.status),
  ).length;

  const warningClaimCount = claims.filter((claim) =>
    isWarnStatus(claim.status),
  ).length;

  const hasSystemError = isSystemErrorRecord(record, sourceStatus);
  const hasFail = isFailStatus(sourceStatus) || errorIssues.length > 0;

  const decisionStatus: J3DecisionStatus = hasSystemError
    ? "SYSTEM_ERROR"
    : hasFail
      ? "NEEDS_REGENERATION"
      : warningIssues.length > 0 || isWarnStatus(sourceStatus)
        ? "ACCEPTED_WITH_WARNINGS"
        : "ACCEPTED";

  const nextAction: J3NextAction =
    decisionStatus === "SYSTEM_ERROR"
      ? "REVIEW_PIPELINE_ERROR"
      : decisionStatus === "NEEDS_REGENERATION"
        ? "REGENERATE_BATCH_I"
        : decisionStatus === "ACCEPTED_WITH_WARNINGS"
          ? "FINALIZE_WITH_WARNINGS"
          : "FINALIZE";

  const canShowToUser =
    decisionStatus === "ACCEPTED" ||
    decisionStatus === "ACCEPTED_WITH_WARNINGS";

  const recommendedFallback =
    decisionStatus === "NEEDS_REGENERATION"
      ? "template_explanation"
      : decisionStatus === "SYSTEM_ERROR"
        ? "human_review"
        : "none";

  const notes = buildDecisionNotes({
    decisionStatus,
    sourceStatus,
    issueCount: issues.length,
    errorCount: errorIssues.length,
    warningCount: warningIssues.length,
    failedClaimCount,
    warningClaimCount,
  });

  return {
    decision_id: buildStableId(
      "j3_decision",
      irId,
      explanationId,
      validationId,
    ),
    created_at: options.createdAt,
    ir_id: irId,
    explanation_id: explanationId || undefined,
    validation_id: validationId || undefined,
    customer_id: customerId || undefined,
    source_validation_status: sourceStatus,
    decision_status: decisionStatus,
    next_action: nextAction,
    feedback_required: decisionStatus === "NEEDS_REGENERATION",
    can_show_to_user: canShowToUser,
    recommended_fallback: recommendedFallback,
    issue_summary: {
      total_issues: issues.length,
      error_count: errorIssues.length,
      warning_count: warningIssues.length,
      failed_claim_count: failedClaimCount,
      warning_claim_count: warningClaimCount,
    },
    notes,
  };
}

function buildRegenerationFeedback(
  record: UnknownRecord,
  decision: J3ValidationDecision,
  options: {
    createdAt: string;
    nextAttempt: number;
  },
): J3RegenerationFeedback {
  const rawIssues = collectFeedbackIssues(record, {
    includeWarnings: true,
  });

  const issues = prioritizeRegenerationIssues(rawIssues, {
    maxWarningIssues: 3,
  });

  const errorCount = issues.filter(
    (issue) => issue.severity === "error",
  ).length;
  const warningCount = issues.filter(
    (issue) => issue.severity === "warning",
  ).length;

  const globalInstructions = buildGlobalRepairInstructions(issues);

  return {
    feedback_id: buildStableId(
      "j3_feedback",
      decision.ir_id,
      decision.explanation_id,
      String(options.nextAttempt),
    ),
    created_at: options.createdAt,
    ir_id: decision.ir_id,
    explanation_id: decision.explanation_id,
    validation_id: decision.validation_id,
    attempt: options.nextAttempt,
    source_batch: "Batch J.3",
    status: "FAIL",
    summary: {
      total_issues: issues.length,
      error_count: errorCount,
      warning_count: warningCount,
    },
    issues,
    global_repair_instructions: globalInstructions,
  };
}


function prioritizeRegenerationIssues(
  issues: J3FeedbackIssue[],
  options: {
    maxWarningIssues: number;
  },
): J3FeedbackIssue[] {
  const originalDeduped = dedupeIssues(issues);
  const deduped = originalDeduped.filter((issue) => !isNoiseIssue(issue));

  const errorIssues = deduped
    .filter((issue) => issue.severity === "error")
    .sort(compareIssuePriority);

  const warningIssues = deduped
    .filter((issue) => issue.severity === "warning")
    .sort(compareIssuePriority)
    .slice(0, options.maxWarningIssues);

  const selected = [...errorIssues, ...warningIssues];

  if (selected.length > 0) {
    return selected;
  }

  /**
   * Safety fallback:
   * If a failed validation produced only filtered noise,
   * keep one original issue so the feedback artifact is not empty.
   */
  return originalDeduped.slice(0, 1);
}

function isNoiseIssue(issue: J3FeedbackIssue): boolean {
  const ruleId = normalizeText(issue.validator_rule_id ?? "");
  const reason = normalizeText(issue.reason);
  const repairInstruction = normalizeText(issue.repair_instruction);

  if (ruleId.includes("j2 claim type unknown")) {
    return true;
  }

  if (reason.includes("unknown claim type")) {
    return true;
  }

  if (repairInstruction.includes("unknown claim type")) {
    return true;
  }

  if (
    issue.failure_type === "schema_or_format_issue" &&
    reason.includes("claim type")
  ) {
    return true;
  }

  if (issue.failure_type === "unknown" && ruleId.includes("claim type")) {
    return true;
  }

  return false;
}
function compareIssuePriority(
  left: J3FeedbackIssue,
  right: J3FeedbackIssue,
): number {
  return getIssuePriorityScore(right) - getIssuePriorityScore(left);
}

function getIssuePriorityScore(issue: J3FeedbackIssue): number {
  let score = 0;

  if (issue.severity === "error") {
    score += 100;
  }

  switch (issue.failure_type) {
    case "prediction_value_mismatch":
      score += 90;
      break;

    case "direction_mismatch":
      score += 85;
      break;

    case "ambiguous_feature_reference":
      score += 80;
      break;

    case "ungrounded_feature":
      score += 75;
      break;

    case "unsupported_concept":
      score += 60;
      break;

    case "missing_required_limitation":
      score += 55;
      break;

    case "schema_or_format_issue":
      score += 40;
      break;

    case "unknown":
    default:
      score += 10;
      break;
  }

  if (issue.validator_rule_id) {
    const ruleId = normalizeText(issue.validator_rule_id);

    if (ruleId.includes("direction")) {
      score += 20;
    }

    if (ruleId.includes("probability") || ruleId.includes("prediction")) {
      score += 20;
    }

    if (ruleId.includes("grounded")) {
      score += 10;
    }

    if (ruleId.includes("claim type unknown")) {
      score -= 80;
    }
  }

  return score;
}
function collectFeedbackIssues(
  record: UnknownRecord,
  options: {
    includeWarnings: boolean;
  },
): J3FeedbackIssue[] {
  const issues: J3FeedbackIssue[] = [];

  const claims = extractClaimValidations(record);

  for (const claim of claims) {
    for (const check of claim.checks) {
      if (isPassStatus(check.status)) {
        continue;
      }

      if (isWarnStatus(check.status) && !options.includeWarnings) {
        continue;
      }

      issues.push(buildIssueFromClaimCheck(claim, check));
    }

    const claimFailed = isFailStatus(claim.status);
    const claimWarned = isWarnStatus(claim.status);

    const hasNonPassCheck = claim.checks.some(
      (check) => !isPassStatus(check.status),
    );

    if ((claimFailed || claimWarned) && !hasNonPassCheck) {
      if (claimWarned && !options.includeWarnings) {
        continue;
      }

      issues.push(buildIssueFromClaimWithoutCheck(claim));
    }
  }

  for (const topLevelIssue of extractTopLevelIssues(record)) {
    if (topLevelIssue.severity === "warning" && !options.includeWarnings) {
      continue;
    }

    issues.push(topLevelIssue);
  }

  return dedupeIssues(issues);
}

function buildIssueFromClaimCheck(
  claim: NormalizedClaim,
  check: NormalizedCheck,
): J3FeedbackIssue {
  const failureType = classifyFailureType({
    ruleId: check.rule_id,
    message: check.message,
    claim,
    check,
  });

  const severity: J3IssueSeverity =
    isFailStatus(check.status) ||
    normalizeSeverity(check.severity) === "error" ||
    isFailStatus(claim.status)
      ? "error"
      : "warning";

  const reason = buildReason(claim, check);
  const repairInstruction = buildRepairInstruction({
    failureType,
    claim,
    check,
  });

  return {
    claim_id: claim.claim_id,
    claim_type: claim.claim_type,
    section: claim.section,
    claim_text: claim.text,
    failure_type: failureType,
    validator_rule_id: check.rule_id,
    severity,
    reason,
    repair_instruction: repairInstruction,
    evidence: normalizeEvidence({
      checkEvidence: check.evidence,
      matchedFeatures: claim.matched_features,
      claimRaw: claim.raw,
      checkRaw: check.raw,
    }),
  };
}

function buildIssueFromClaimWithoutCheck(
  claim: NormalizedClaim,
): J3FeedbackIssue {
  const failureType = classifyFailureType({
    ruleId: undefined,
    message: `Claim status is ${claim.status}.`,
    claim,
    check: undefined,
  });

  const severity: J3IssueSeverity = isFailStatus(claim.status)
    ? "error"
    : "warning";

  return {
    claim_id: claim.claim_id,
    claim_type: claim.claim_type,
    section: claim.section,
    claim_text: claim.text,
    failure_type: failureType,
    severity,
    reason: `The validator marked this claim as ${claim.status}, but no detailed failed check was provided.`,
    repair_instruction: buildRepairInstruction({
      failureType,
      claim,
      check: undefined,
    }),
    evidence: normalizeEvidence({
      matchedFeatures: claim.matched_features,
      claimRaw: claim.raw,
    }),
  };
}

function classifyFailureType(input: {
  ruleId?: string;
  message?: string;
  claim?: NormalizedClaim;
  check?: NormalizedCheck;
}): J3FailureType {
  const rule = normalizeText(input.ruleId ?? "");
  const message = normalizeText(input.message ?? "");
  const claimType = normalizeText(input.claim?.claim_type ?? "");
  const claimText = normalizeText(input.claim?.text ?? "");

  if (
    rule.includes("prediction") ||
    rule.includes("probability") ||
    message.includes("probability") ||
    message.includes("xác suất") ||
    message.includes("threshold") ||
    message.includes("ngưỡng")
  ) {
    return "prediction_value_mismatch";
  }

  if (
    rule.includes("direction") ||
    rule.includes("sign") ||
    message.includes("direction") ||
    message.includes("polarity") ||
    message.includes("opposite") ||
    message.includes("contradict") ||
    message.includes("trái chiều") ||
    message.includes("ngược chiều")
  ) {
    if (isAmbiguousFeatureReference(input.claim)) {
      return "ambiguous_feature_reference";
    }

    return "direction_mismatch";
  }

  if (
    rule.includes("feature") &&
    (rule.includes("grounded") ||
      rule.includes("exist") ||
      rule.includes("unsupported") ||
      rule.includes("invent"))
  ) {
    if (isAmbiguousFeatureReference(input.claim)) {
      return "ambiguous_feature_reference";
    }

    return "ungrounded_feature";
  }

  if (
    rule.includes("concept") ||
    claimType.includes("concept") ||
    message.includes("concept")
  ) {
    return "unsupported_concept";
  }

  if (
    rule.includes("limitation") ||
    claimType.includes("limitation") ||
    message.includes("causal") ||
    message.includes("nhân quả") ||
    message.includes("final credit") ||
    message.includes("quyết định tín dụng") ||
    message.includes("kết luận chắc chắn")
  ) {
    return "missing_required_limitation";
  }

  if (
    rule.includes("schema") ||
    rule.includes("json") ||
    rule.includes("required") ||
    rule.includes("raw_technical") ||
    rule.includes("technical") ||
    rule.includes("forbidden") ||
    rule.includes("wording") ||
    message.includes("schema") ||
    message.includes("json") ||
    message.includes("required") ||
    message.includes("technical") ||
    message.includes("forbidden")
  ) {
    return "schema_or_format_issue";
  }

  if (
    claimText.includes("chắc chắn") ||
    claimText.includes("sẽ không trả") ||
    claimText.includes("không thể trả") ||
    claimText.includes("gian lận")
  ) {
    return "schema_or_format_issue";
  }

  return "unknown";
}

function buildRepairInstruction(input: {
  failureType: J3FailureType;
  claim: NormalizedClaim;
  check?: NormalizedCheck;
}): string {
  const claimText = input.claim.text || "the failed claim";
  const evidence = input.check?.evidence ?? {};
  const matchedFeatures = getMatchedFeatures(input.claim, evidence);

  switch (input.failureType) {
    case "prediction_value_mismatch":
      return [
        "Rewrite the prediction section using only the probability, threshold, predicted label, and threshold comparison from the IR.",
        "Do not round or alter numeric values unless the IR already provides a display string.",
        "Do not strengthen the risk statement beyond the IR prediction.",
      ].join(" ");

    case "direction_mismatch":
      return [
        `Fix the direction of the claim: "${claimText}".`,
        "If the IR says the factor increases risk, describe it as increasing risk.",
        "If the IR says the factor decreases risk, describe it as decreasing risk.",
        "Do not flip the sign or use wording that implies the opposite direction.",
      ].join(" ");

    case "ambiguous_feature_reference":
      return [
        `The claim "${claimText}" is ambiguous because it may match multiple IR features.`,
        "Regenerate the sentence using a unique feature label.",
        "For categorical/one-hot features, include the category value or feature_id.",
        buildMatchedFeatureHint(matchedFeatures),
      ]
        .filter(Boolean)
        .join(" ");

    case "ungrounded_feature":
      return [
        `The claim "${claimText}" is not clearly grounded in an IR feature.`,
        "Remove it or replace it with a claim using an allowed feature/concept from the IR.",
        "Prefer the exact display name, unique_label, or concept-level wording provided in the prompt contract.",
      ].join(" ");

    case "unsupported_concept":
      return [
        `The concept claim "${claimText}" is not clearly grounded in known IR concepts.`,
        "Use only concept names/groups available in the IR contract.",
        "If the concept is paraphrased, rewrite it closer to the IR display name.",
      ].join(" ");

    case "missing_required_limitation":
      return [
        "Rewrite the limitations section so it explicitly says all required limitations:",
        "the explanation only describes contribution to the model prediction;",
        "it does not prove real-world causality;",
        "it is not the final credit decision;",
        "and it is not a certain conclusion.",
      ].join(" ");

    case "schema_or_format_issue":
      return [
        "Regenerate the explanation as valid JSON matching the required output schema.",
        "Do not include markdown.",
        "Do not include raw technical feature names, forbidden wording, or unsupported certainty claims.",
      ].join(" ");

    case "unknown":
    default:
      return [
        `The validator rejected or warned about the claim "${claimText}".`,
        "Rewrite this part to stay closer to the IR evidence.",
        "Use only facts, directions, numeric values, display names, and concepts from the prompt contract.",
        "If unsure, omit the claim instead of inventing or paraphrasing too aggressively.",
      ].join(" ");
  }
}

function buildMatchedFeatureHint(features: unknown[]): string {
  const normalized = features
    .map((feature) => asObject(feature))
    .filter(Boolean)
    .map((feature) => {
      const featureId = getFirstString(feature, ["feature_id", "featureId"]);
      const displayName = getFirstString(feature, [
        "display_name",
        "displayName",
      ]);
      const direction = getFirstString(feature, [
        "contribution_direction",
        "contributionDirection",
        "direction",
      ]);
      const contribution = getFirstNumber(feature, [
        "contribution_value",
        "contributionValue",
        "shap_value",
        "shapValue",
      ]);

      return {
        featureId,
        displayName,
        direction,
        contribution,
      };
    })
    .filter((item) => item.featureId || item.displayName)
    .slice(0, 8);

  if (normalized.length === 0) {
    return "";
  }

  const options = normalized
    .map((item) => {
      const label = item.featureId
        ? `${item.displayName || "feature"} (${item.featureId})`
        : item.displayName;

      const direction = item.direction ? `direction=${item.direction}` : "";
      const contribution =
        typeof item.contribution === "number"
          ? `contribution=${item.contribution}`
          : "";

      return [label, direction, contribution].filter(Boolean).join(", ");
    })
    .join("; ");

  return `Candidate matched IR features: ${options}. Choose the exact intended one and mention it unambiguously.`;
}

function buildReason(claim: NormalizedClaim, check: NormalizedCheck): string {
  const parts = [
    check.message || `Validator check ${check.rule_id ?? "unknown"} failed.`,
  ];

  if (check.rule_id) {
    parts.push(`Rule: ${check.rule_id}.`);
  }

  if (claim.status) {
    parts.push(`Claim status: ${claim.status}.`);
  }

  return parts.join(" ");
}

function normalizeEvidence(input: {
  checkEvidence?: Record<string, unknown>;
  matchedFeatures?: unknown[];
  claimRaw?: UnknownRecord;
  checkRaw?: UnknownRecord;
}): Record<string, unknown> | undefined {
  const evidence: Record<string, unknown> = {};

  if (input.checkEvidence && Object.keys(input.checkEvidence).length > 0) {
    evidence.check_evidence = input.checkEvidence;
  }

  if (input.matchedFeatures && input.matchedFeatures.length > 0) {
    evidence.matched_features = input.matchedFeatures;
  }

  if (input.checkRaw?.rule_id || input.checkRaw?.ruleId) {
    evidence.rule_id = input.checkRaw.rule_id ?? input.checkRaw.ruleId;
  }

  return Object.keys(evidence).length > 0 ? evidence : undefined;
}

function buildGlobalRepairInstructions(issues: J3FeedbackIssue[]): string[] {
  const instructions = new Set<string>();
  const filteredIssues = issues.filter((issue) => !isNoiseIssue(issue));
  instructions.add("Use only facts provided in the Explanation IR contract.");
  instructions.add(
    "Do not invent new customer facts, causes, recommendations, or unsupported conclusions.",
  );
  instructions.add(
    "Keep probability, threshold, contribution values, signs, and risk directions exactly aligned with IR.",
  );
  instructions.add(
    "Return only valid JSON matching the Batch I output schema.",
  );

  for (const issue of filteredIssues) {
    switch (issue.failure_type) {
      case "prediction_value_mismatch":
        instructions.add(
          "Prediction claims must use the exact IR probability, threshold, label, and threshold comparison.",
        );
        break;

      case "direction_mismatch":
        instructions.add(
          "Do not flip feature direction: increases_risk must be written as increasing risk; decreases_risk must be written as decreasing risk.",
        );
        break;

      case "ambiguous_feature_reference":
        instructions.add(
          "For duplicated display names or one-hot categorical features, mention the category value or feature_id to make the feature unambiguous.",
        );
        break;

      case "ungrounded_feature":
        instructions.add(
          "Remove unsupported feature claims or replace them with feature/concept names that exist in the IR.",
        );
        break;

      case "unsupported_concept":
        instructions.add(
          "Use concept names close to the IR concept display names; avoid broad paraphrases that the validator cannot ground.",
        );
        break;

      case "missing_required_limitation":
        instructions.add(
          "The limitations section must say: not causal, not final credit decision, not a certain conclusion, and only describes model contribution.",
        );
        break;

      case "schema_or_format_issue":
        instructions.add(
          "Avoid markdown, raw technical names, forbidden wording, and unsupported certainty claims.",
        );
        break;

      case "unknown":
      default:
        instructions.add(
          "For any uncertain claim, prefer omitting it rather than creating a weakly grounded statement.",
        );
        break;
    }
  }

  return Array.from(instructions);
}

function extractClaimValidations(record: UnknownRecord): NormalizedClaim[] {
  const candidates = [
    record.claim_validations,
    record.claimValidations,
    record.claim_results,
    record.claimResults,
    record.claim_level_results,
    record.claimLevelResults,
    record.claims,
    asObject(record.validation)?.claim_validations,
    asObject(record.validation)?.claimValidations,
    asObject(record.validation)?.claim_results,
    asObject(record.validation)?.claimResults,
    asObject(record.claim_extraction)?.claims,
    asObject(record.claimExtraction)?.claims,
  ];

  const array = candidates.find(Array.isArray) as unknown[] | undefined;

  if (!array) {
    return [];
  }

  return array
    .map((item) => normalizeClaim(item))
    .filter((item): item is NormalizedClaim => Boolean(item));
}

function normalizeClaim(value: unknown): NormalizedClaim | null {
  const obj = asObject(value);

  if (!obj) {
    return null;
  }

  const checksRaw = [
    obj.checks,
    obj.validation_checks,
    obj.validationChecks,
    obj.issues,
  ].find(Array.isArray) as unknown[] | undefined;

  const checks = (checksRaw ?? [])
    .map((item) => normalizeCheck(item))
    .filter((item): item is NormalizedCheck => Boolean(item));

  const matchedFeaturesRaw = [
    obj.matched_features,
    obj.matchedFeatures,
    obj.matched_ir_features,
    obj.matchedIrFeatures,
  ].find(Array.isArray) as unknown[] | undefined;

  return {
    claim_id: getFirstString(obj, ["claim_id", "claimId", "id"]),
    claim_type: getFirstString(obj, ["claim_type", "claimType", "type"]),
    section: getFirstString(obj, [
      "section",
      "source_section",
      "sourceSection",
    ]),
    text: getFirstString(obj, [
      "text",
      "claim_text",
      "claimText",
      "original_text",
      "originalText",
    ]),
    status: getFirstString(
      obj,
      ["status", "validation_status", "validationStatus"],
      "UNKNOWN",
    ),
    checks,
    matched_features: matchedFeaturesRaw ?? [],
    raw: obj,
  };
}

function normalizeCheck(value: unknown): NormalizedCheck | null {
  const obj = asObject(value);

  if (!obj) {
    return null;
  }

  return {
    rule_id: getFirstString(obj, ["rule_id", "ruleId", "id"]),
    status: getFirstString(obj, ["status", "result"], "UNKNOWN"),
    severity: getFirstString(obj, ["severity", "level"]),
    message: getFirstString(obj, ["message", "reason", "description"]),
    evidence: asObject(obj.evidence),
    raw: obj,
  };
}

function extractTopLevelIssues(record: UnknownRecord): J3FeedbackIssue[] {
  const issues: J3FeedbackIssue[] = [];
  const validation = asObject(record.validation);

  const candidates = [
    record.blocking_issues,
    record.blockingIssues,
    record.warnings,
    record.errors,
    validation?.blocking_issues,
    validation?.blockingIssues,
    validation?.warnings,
    validation?.errors,
  ];

  for (const candidate of candidates) {
    if (!Array.isArray(candidate)) {
      continue;
    }

    for (const item of candidate) {
      const obj = asObject(item);

      if (!obj) {
        continue;
      }

      const status = getFirstString(obj, ["status"], "FAIL");
      const message = getFirstString(obj, ["message", "reason", "description"]);
      const ruleId = getFirstString(obj, ["rule_id", "ruleId", "id"]);

      const fakeClaim: NormalizedClaim = {
        claim_id: getFirstString(obj, ["claim_id", "claimId"]),
        claim_type: getFirstString(obj, ["claim_type", "claimType"]),
        section: getFirstString(obj, ["section"]),
        text: getFirstString(obj, ["claim_text", "claimText", "text"], message),
        status,
        checks: [],
        matched_features: [],
        raw: obj,
      };

      const fakeCheck: NormalizedCheck = {
        rule_id: ruleId,
        status,
        severity: getFirstString(obj, ["severity", "level"]),
        message,
        evidence: asObject(obj.evidence),
        raw: obj,
      };

      issues.push(buildIssueFromClaimCheck(fakeClaim, fakeCheck));
    }
  }

  return issues;
}

function isAmbiguousFeatureReference(claim?: NormalizedClaim): boolean {
  if (!claim) {
    return false;
  }

  const features = claim.matched_features
    .map((item) => asObject(item))
    .filter(Boolean);

  if (features.length <= 1) {
    return false;
  }

  const displayNames = features
    .map((feature) => getFirstString(feature, ["display_name", "displayName"]))
    .filter(Boolean);

  const uniqueDisplayNames = new Set(displayNames.map(normalizeText));

  if (displayNames.length > 1 && uniqueDisplayNames.size === 1) {
    return true;
  }

  const directions = features
    .map((feature) =>
      getFirstString(feature, [
        "contribution_direction",
        "contributionDirection",
        "direction",
      ]),
    )
    .filter(Boolean);

  if (new Set(directions.map(normalizeText)).size > 1) {
    return true;
  }

  return false;
}

function getMatchedFeatures(
  claim: NormalizedClaim,
  checkEvidence: Record<string, unknown>,
): unknown[] {
  if (claim.matched_features.length > 0) {
    return claim.matched_features;
  }

  const evidenceMatched = checkEvidence.matched_features;

  if (Array.isArray(evidenceMatched)) {
    return evidenceMatched;
  }

  return [];
}

function isSystemErrorRecord(record: UnknownRecord, status: string): boolean {
  const normalized = normalizeStatus(status);

  if (normalized.includes("SYSTEM_ERROR") || normalized.includes("ERROR")) {
    return true;
  }

  const irId = getIrId(record);
  const explanationId = getExplanationId(record);

  if (!irId || irId === "unknown_ir") {
    return true;
  }

  if (!explanationId) {
    return true;
  }

  return false;
}

function getValidationStatus(record: UnknownRecord): string {
  const validation = asObject(record.validation);

  return getFirstString(
    record,
    ["status", "validation_status", "validationStatus"],
    getFirstString(
      validation,
      ["status", "validation_status", "validationStatus"],
      "UNKNOWN",
    ),
  );
}

function getIrId(record: UnknownRecord): string {
  return getFirstString(
    record,
    ["ir_id", "irId", "source_ir_id", "sourceIrId"],
    getFirstString(
      asObject(record.claim_extraction),
      ["ir_id", "irId", "source_ir_id", "sourceIrId"],
      "unknown_ir",
    ),
  );
}

function getExplanationId(record: UnknownRecord): string {
  return getFirstString(
    record,
    ["explanation_id", "explanationId"],
    getFirstString(asObject(record.claim_extraction), [
      "explanation_id",
      "explanationId",
    ]),
  );
}

function getValidationId(record: UnknownRecord): string {
  return getFirstString(record, ["validation_id", "validationId", "id"]);
}

function getCustomerIdFromValidation(record: UnknownRecord): string {
  const customer = asObject(record.customer);

  return getFirstString(
    record,
    ["customer_id", "customerId", "SK_ID_CURR", "sk_id_curr"],
    getFirstString(customer, [
      "customer_id",
      "customerId",
      "SK_ID_CURR",
      "sk_id_curr",
    ]),
  );
}

function buildDecisionNotes(input: {
  decisionStatus: J3DecisionStatus;
  sourceStatus: string;
  issueCount: number;
  errorCount: number;
  warningCount: number;
  failedClaimCount: number;
  warningClaimCount: number;
}): string[] {
  const notes: string[] = [];

  notes.push(`Source J.2 validation status: ${input.sourceStatus}.`);

  if (input.decisionStatus === "ACCEPTED") {
    notes.push(
      "No blocking issue was detected. The explanation can be finalized.",
    );
  }

  if (input.decisionStatus === "ACCEPTED_WITH_WARNINGS") {
    notes.push(
      "No blocking issue was detected, but warnings should remain visible in audit artifacts.",
    );
  }

  if (input.decisionStatus === "NEEDS_REGENERATION") {
    notes.push(
      "At least one blocking issue was detected. Build feedback and regenerate via Batch I manually or through a future controlled loop.",
    );
  }

  if (input.decisionStatus === "SYSTEM_ERROR") {
    notes.push(
      "The validation record appears incomplete or malformed. Review Batch J.1/J.2 pipeline before regeneration.",
    );
  }

  notes.push(
    `Issues: ${input.issueCount}; errors: ${input.errorCount}; warnings: ${input.warningCount}; failed claims: ${input.failedClaimCount}; warning claims: ${input.warningClaimCount}.`,
  );

  return notes;
}

function buildSummary(input: {
  createdAt: string;
  runMode: J3RunMode;
  generatorType: J3GeneratorType;
  paths: J3Paths;
  validationRecords: UnknownRecord[];
  decisions: J3ValidationDecision[];
  regenerationFeedback: J3RegenerationFeedback[];
  finalizationCandidates: J3FinalizationCandidate[];
  generateFeedbackForWarnings: boolean;
  nextAttempt: number;
}): J3Summary {
  const acceptedRecords = input.decisions.filter(
    (item) => item.decision_status === "ACCEPTED",
  ).length;

  const acceptedWithWarningsRecords = input.decisions.filter(
    (item) => item.decision_status === "ACCEPTED_WITH_WARNINGS",
  ).length;

  const needsRegenerationRecords = input.decisions.filter(
    (item) => item.decision_status === "NEEDS_REGENERATION",
  ).length;

  const systemErrorRecords = input.decisions.filter(
    (item) => item.decision_status === "SYSTEM_ERROR",
  ).length;

  const totalFeedbackIssues = input.regenerationFeedback.reduce(
    (sum, feedback) => sum + feedback.summary.total_issues,
    0,
  );

  const totalFeedbackErrors = input.regenerationFeedback.reduce(
    (sum, feedback) => sum + feedback.summary.error_count,
    0,
  );

  const totalFeedbackWarnings = input.regenerationFeedback.reduce(
    (sum, feedback) => sum + feedback.summary.warning_count,
    0,
  );

  return {
    report_name: "Batch J.3 Validation Decision & Feedback Summary",
    created_at: input.createdAt,
    batch: "Batch J.3",
    batch_version: "v1.0",
    mode: "validation_decision_and_feedback_builder",
    run_mode: input.runMode,
    generator_type: input.generatorType,
    input_paths: {
      validation_jsonl_path: input.paths.validationJsonlPath,
      validation_summary_json_path: input.paths.validationSummaryJsonPath,
      validation_failures_json_path: input.paths.validationFailuresJsonPath,
    },
    output_paths: {
      validation_decisions_jsonl_path: input.paths.validationDecisionsJsonlPath,
      regeneration_feedback_jsonl_path:
        input.paths.regenerationFeedbackJsonlPath,
      regeneration_feedback_summary_json_path:
        input.paths.regenerationFeedbackSummaryJsonPath,
      finalization_candidates_jsonl_path:
        input.paths.finalizationCandidatesJsonlPath,
      validation_decision_report_md_path:
        input.paths.validationDecisionReportMdPath,
    },
    counts: {
      validation_records: input.validationRecords.length,
      accepted_records: acceptedRecords,
      accepted_with_warnings_records: acceptedWithWarningsRecords,
      needs_regeneration_records: needsRegenerationRecords,
      system_error_records: systemErrorRecords,
      regeneration_feedback_records: input.regenerationFeedback.length,
      finalization_candidate_records: input.finalizationCandidates.length,
      total_feedback_issues: totalFeedbackIssues,
      total_feedback_errors: totalFeedbackErrors,
      total_feedback_warnings: totalFeedbackWarnings,
    },
    policy: {
      generate_feedback_for_warnings: input.generateFeedbackForWarnings,
      next_attempt: input.nextAttempt,
      auto_loop_enabled: false,
      calls_llm: false,
      calls_bedrock: false,
    },
  };
}

async function writeArtifacts(input: {
  paths: J3Paths;
  decisions: J3ValidationDecision[];
  regenerationFeedback: J3RegenerationFeedback[];
  finalizationCandidates: J3FinalizationCandidate[];
  summary: J3Summary;
}): Promise<void> {
  await mkdir(input.paths.outputDir, { recursive: true });

  await writeJsonl(input.paths.validationDecisionsJsonlPath, input.decisions);
  await writeJsonl(
    input.paths.regenerationFeedbackJsonlPath,
    input.regenerationFeedback,
  );
  await writeJsonl(
    input.paths.finalizationCandidatesJsonlPath,
    input.finalizationCandidates,
  );

  await writeFile(
    input.paths.regenerationFeedbackSummaryJsonPath,
    JSON.stringify(input.summary, null, 2),
    "utf-8",
  );

  await writeFile(
    input.paths.validationDecisionReportMdPath,
    buildMarkdownReport(input.summary, input.decisions),
    "utf-8",
  );
}

function buildMarkdownReport(
  summary: J3Summary,
  decisions: J3ValidationDecision[],
): string {
  const lines: string[] = [];

  lines.push("# Batch J.3 Validation Decision & Feedback Report");
  lines.push("");
  lines.push(`Created at: ${summary.created_at}`);
  lines.push(`Run mode: \`${summary.run_mode}\``);
  lines.push(`Generator type: \`${summary.generator_type}\``);
  lines.push("");
  lines.push("## Summary");
  lines.push("");
  lines.push(`- Validation records: ${summary.counts.validation_records}`);
  lines.push(`- Accepted records: ${summary.counts.accepted_records}`);
  lines.push(
    `- Accepted with warnings records: ${summary.counts.accepted_with_warnings_records}`,
  );
  lines.push(
    `- Needs regeneration records: ${summary.counts.needs_regeneration_records}`,
  );
  lines.push(`- System error records: ${summary.counts.system_error_records}`);
  lines.push(
    `- Regeneration feedback records: ${summary.counts.regeneration_feedback_records}`,
  );
  lines.push(
    `- Total feedback issues: ${summary.counts.total_feedback_issues}`,
  );
  lines.push(
    `- Total feedback errors: ${summary.counts.total_feedback_errors}`,
  );
  lines.push(
    `- Total feedback warnings: ${summary.counts.total_feedback_warnings}`,
  );
  lines.push("");
  lines.push("## Policy");
  lines.push("");
  lines.push(`- Auto loop enabled: \`${summary.policy.auto_loop_enabled}\``);
  lines.push(`- Calls LLM: \`${summary.policy.calls_llm}\``);
  lines.push(`- Calls Bedrock: \`${summary.policy.calls_bedrock}\``);
  lines.push(
    `- Generate feedback for warnings: \`${summary.policy.generate_feedback_for_warnings}\``,
  );
  lines.push(`- Next attempt: \`${summary.policy.next_attempt}\``);
  lines.push("");
  lines.push("## Per-record decisions");
  lines.push("");
  lines.push(
    "| # | Decision | Next action | IR ID | Explanation ID | Errors | Warnings | Can show |",
  );
  lines.push("|---:|---|---|---|---|---:|---:|---|");

  decisions.forEach((decision, index) => {
    lines.push(
      [
        `| ${index + 1}`,
        decision.decision_status,
        decision.next_action,
        `\`${decision.ir_id}\``,
        decision.explanation_id ? `\`${decision.explanation_id}\`` : "",
        String(decision.issue_summary.error_count),
        String(decision.issue_summary.warning_count),
        String(decision.can_show_to_user),
      ].join(" | ") + " |",
    );
  });

  lines.push("");
  lines.push("## Output artifacts");
  lines.push("");
  lines.push(
    `- Validation decisions: \`${summary.output_paths.validation_decisions_jsonl_path}\``,
  );
  lines.push(
    `- Regeneration feedback: \`${summary.output_paths.regeneration_feedback_jsonl_path}\``,
  );
  lines.push(
    `- Feedback summary: \`${summary.output_paths.regeneration_feedback_summary_json_path}\``,
  );
  lines.push(
    `- Finalization candidates: \`${summary.output_paths.finalization_candidates_jsonl_path}\``,
  );

  return lines.join("\n");
}

async function readJsonlFile<T>(filePath: string): Promise<T[]> {
  const content = await readFile(filePath, "utf-8");
  const records: T[] = [];

  const lines = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];

    try {
      records.push(JSON.parse(line) as T);
    } catch (error) {
      throw new Error(
        `Failed to parse JSONL file at ${filePath}, line ${index + 1}: ${
          error instanceof Error ? error.message : "Unknown parse error"
        }`,
      );
    }
  }

  return records;
}

async function writeJsonl<T>(filePath: string, records: T[]): Promise<void> {
  const content = records.map((record) => JSON.stringify(record)).join("\n");
  await writeFile(
    filePath,
    content + (records.length > 0 ? "\n" : ""),
    "utf-8",
  );
}

function dedupeIssues(issues: J3FeedbackIssue[]): J3FeedbackIssue[] {
  const seen = new Set<string>();
  const output: J3FeedbackIssue[] = [];

  for (const issue of issues) {
    const key = [
      issue.claim_id ?? "",
      issue.validator_rule_id ?? "",
      issue.claim_text,
      issue.failure_type,
      issue.severity,
    ].join("::");

    if (seen.has(key)) {
      continue;
    }

    seen.add(key);
    output.push(issue);
  }

  return output;
}

function isPassStatus(value: string): boolean {
  return normalizeStatus(value) === "PASS";
}

function isWarnStatus(value: string): boolean {
  const status = normalizeStatus(value);
  return status === "WARN" || status === "WARNING" || status.includes("WARN");
}

function isFailStatus(value: string): boolean {
  const status = normalizeStatus(value);
  return status === "FAIL" || status.includes("FAIL");
}

function normalizeStatus(value: string): string {
  return String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "_");
}

function normalizeSeverity(value: string | undefined): J3IssueSeverity | "" {
  const normalized = String(value ?? "")
    .trim()
    .toLowerCase();

  if (
    normalized === "error" ||
    normalized === "critical" ||
    normalized === "fail"
  ) {
    return "error";
  }

  if (normalized === "warning" || normalized === "warn") {
    return "warning";
  }

  return "";
}

function normalizeText(value: string): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ");
}

function asObject(value: unknown): UnknownRecord | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }

  return value as UnknownRecord;
}

function getFirstString(
  obj: UnknownRecord | undefined,
  keys: string[],
  fallback = "",
): string {
  if (!obj) {
    return fallback;
  }

  for (const key of keys) {
    const value = obj[key];

    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }

    if (typeof value === "number" && Number.isFinite(value)) {
      return String(value);
    }

    if (typeof value === "boolean") {
      return String(value);
    }
  }

  return fallback;
}

function getFirstNumber(
  obj: UnknownRecord | undefined,
  keys: string[],
): number | undefined {
  if (!obj) {
    return undefined;
  }

  for (const key of keys) {
    const value = obj[key];

    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }

    if (typeof value === "string") {
      const parsed = Number(value);

      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }

  return undefined;
}

function buildStableId(
  prefix: string,
  ...parts: Array<string | undefined>
): string {
  const raw = [prefix, ...parts.filter(Boolean)].join("_");

  return raw
    .trim()
    .replace(/[^a-zA-Z0-9_-]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}
