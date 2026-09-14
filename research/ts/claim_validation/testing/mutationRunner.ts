import { execFile } from "node:child_process";
import {
  cp,
  mkdtemp,
  mkdir,
  readFile,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import thresholds from "../../../../config/research/ts-validation/claim_validation_test_thresholds_v1.json";

const execFileAsync = promisify(execFile);
const testFiles = [
  "tests/research/ts/claimValidationBoundaries.test.ts",
  "tests/research/ts/claimValidationConceptAggregation.test.ts",
  "tests/research/ts/claimValidationEvidenceExposure.test.ts",
  "tests/research/ts/claimValidationFactConsistency.test.ts",
  "tests/research/ts/claimValidationSubtypeRouting.test.ts",
];

type Mutation = {
  id: string;
  description: string;
  file: string;
  search: string;
  replacement: string;
};

const mutations: Mutation[] = [
  {
    id: "M01_CONCEPT_MIXED_OR",
    description: "Treat either sign as a mixed aggregate.",
    file: "research/ts/claim_validation/validators/shared.ts",
    search:
      'values.has("increase_risk") && values.has("decrease_risk")',
    replacement:
      'values.has("increase_risk") || values.has("decrease_risk")',
  },
  {
    id: "M02_S5_EXPOSURE_REVERSED",
    description: "Reverse allowed and forbidden feature exposure.",
    file: "research/ts/claim_validation/validators/shared.ts",
    search:
      "return view.allowed_feature_ids.includes(featureId)\n"
      + '    ? "EXPOSED_ALLOWED"\n'
      + '    : "EXPOSED_FORBIDDEN";',
    replacement:
      "return view.allowed_feature_ids.includes(featureId)\n"
      + '    ? "EXPOSED_FORBIDDEN"\n'
      + '    : "EXPOSED_ALLOWED";',
  },
  {
    id: "M03_PREDICTION_EQUALITY_REVERSED",
    description: "Contradict matching prediction labels.",
    file:
      "research/ts/claim_validation/validators/predictionFeatureConcept.ts",
    search:
      "expected.prediction_label !== observed.prediction_label",
    replacement:
      "expected.prediction_label === observed.prediction_label",
  },
  {
    id: "M04_UNCERTAINTY_POLICY_REVERSED",
    description: "Ground probability hedge when the policy is false.",
    file: "research/ts/claim_validation/validators/policyClaims.ts",
    search:
      'case "PROBABILITY_HEDGE":\n'
      + "      return {\n"
      + "        grounded: payload.narrative_policy.must_include_uncertainty === true",
    replacement:
      'case "PROBABILITY_HEDGE":\n'
      + "      return {\n"
      + "        grounded: payload.narrative_policy.must_include_uncertainty === false",
  },
  {
    id: "M05_MAGNITUDE_ORDER_REVERSED",
    description: "Reverse magnitude overstatement and understatement.",
    file:
      "research/ts/claim_validation/validators/numericRankingMagnitude.ts",
    search: "return order[expected] - order[observed];",
    replacement: "return order[observed] - order[expected];",
  },
  {
    id: "M06_EXACT_GATE_DISABLED",
    description: "Remove EXACT_MATCH from fact-consistency enforcement.",
    file: "research/ts/claim_validation/factConsistency.ts",
    search: "  REASON_CODE.EXACT_MATCH,\n",
    replacement: "",
  },
  {
    id: "M07_TOLERANCE_COMPARISON_REVERSED",
    description: "Reject values inside tolerance and accept values outside.",
    file: "research/ts/claim_validation/factConsistency.ts",
    search: "comparison.difference > comparison.tolerance",
    replacement: "comparison.difference <= comparison.tolerance",
  },
  {
    id: "M08_FORBIDDEN_POLICY_AND",
    description: "Require both feature and concept violations.",
    file: "research/ts/claim_validation/result.ts",
    search:
      'exposure.feature === "EXPOSED_FORBIDDEN" ||\n    exposure.concept === "EXPOSED_FORBIDDEN"',
    replacement:
      'exposure.feature === "EXPOSED_FORBIDDEN" &&\n    exposure.concept === "EXPOSED_FORBIDDEN"',
  },
  {
    id: "M09_EPSILON_STRICT",
    description: "Exclude exact epsilon from the neutral boundary.",
    file: "research/ts/claim_validation/validators/shared.ts",
    search:
      "Math.abs(feature.shap_value) <=\n      CLAIM_VALIDATION_POLICY.near_zero_shap_epsilon",
    replacement:
      "Math.abs(feature.shap_value) <\n      CLAIM_VALIDATION_POLICY.near_zero_shap_epsilon",
  },
  {
    id: "M10_NUMERIC_TOLERANCE_STRICT",
    description: "Reject a numeric value exactly at tolerance.",
    file:
      "research/ts/claim_validation/validators/numericRankingMagnitude.ts",
    search: "if (delta <= tolerance) {",
    replacement: "if (delta < tolerance) {",
  },
  {
    id: "M11_LIMITATION_UNRELATED_RULE",
    description: "Support non-causal limitation when causality is allowed.",
    file: "research/ts/claim_validation/validators/policyClaims.ts",
    search:
      "payload.constraints.claim_policy.allow_causal_claim === false",
    replacement:
      "payload.constraints.claim_policy.allow_causal_claim === true",
  },
  {
    id: "M12_DISTRIBUTED_COUNT_WIDENED",
    description: "Require three features for MULTIPLE_FEATURES.",
    file: "research/ts/claim_validation/validators/policyClaims.ts",
    search: "grounded: view.exposed_features.length > 1",
    replacement: "grounded: view.exposed_features.length > 2",
  },
];

async function main(): Promise<void> {
  const repositoryRoot = process.cwd();
  const outputPath = path.resolve(
    argumentValue("--output") ?? "reports/claim-validation-mutation.json",
  );
  const workspace = await mkdtemp(
    path.join(os.tmpdir(), "claim-validation-mutation-"),
  );
  const results: Array<Record<string, unknown>> = [];
  try {
    for (const mutation of mutations) {
      const mutantRoot = path.join(workspace, mutation.id);
      await prepareMutant(repositoryRoot, mutantRoot);
      await applyMutation(mutantRoot, mutation);
      const startedAt = Date.now();
      const execution = await runTests(mutantRoot);
      results.push({
        id: mutation.id,
        description: mutation.description,
        file: mutation.file,
        killed: execution.exitCode !== 0,
        exit_code: execution.exitCode,
        duration_ms: Date.now() - startedAt,
        output_tail: execution.output.slice(-2000),
      });
      await rm(mutantRoot, { recursive: true, force: true });
    }
  } finally {
    await rm(workspace, { recursive: true, force: true });
  }
  const killed = results.filter((result) => result.killed === true).length;
  const score = mutations.length === 0 ? 0 : (killed / mutations.length) * 100;
  const report = {
    schema_version: "claim_validation_mutation_report_v1",
    runner: "controlled_source_mutation",
    generated_at: new Date().toISOString(),
    production_source_mutated_in_isolated_copies: true,
    mutation_count: mutations.length,
    killed_count: killed,
    survived_count: mutations.length - killed,
    mutation_score: score,
    thresholds: thresholds.mutation,
    pass:
      mutations.length - killed <= thresholds.mutation.critical_survivors &&
      score >= thresholds.mutation.critical_score,
    mutations: results,
  };
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(report, null, 2));
  if (!report.pass) process.exitCode = 1;
}

async function prepareMutant(
  repositoryRoot: string,
  mutantRoot: string,
): Promise<void> {
  await mkdir(mutantRoot, { recursive: true });
  for (const directory of ["research", "contracts", "config", "tests"]) {
    await cp(
      path.join(repositoryRoot, directory),
      path.join(mutantRoot, directory),
      { recursive: true },
    );
  }
  await symlink(
    path.join(repositoryRoot, "node_modules"),
    path.join(mutantRoot, "node_modules"),
    "dir",
  );
  await symlink(
    path.join(repositoryRoot, "data"),
    path.join(mutantRoot, "data"),
    "dir",
  );
}

async function applyMutation(
  mutantRoot: string,
  mutation: Mutation,
): Promise<void> {
  const filePath = path.join(mutantRoot, mutation.file);
  const source = await readFile(filePath, "utf8");
  const occurrences = source.split(mutation.search).length - 1;
  if (occurrences !== 1) {
    throw new Error(
      `${mutation.id} expected one source match, found ${occurrences}.`,
    );
  }
  await writeFile(
    filePath,
    source.replace(mutation.search, mutation.replacement),
    "utf8",
  );
}

async function runTests(
  mutantRoot: string,
): Promise<{ exitCode: number; output: string }> {
  try {
    const result = await execFileAsync(
      process.execPath,
      ["--import", "tsx", "--test", ...testFiles],
      {
        cwd: mutantRoot,
        timeout: 60_000,
        maxBuffer: 10 * 1024 * 1024,
      },
    );
    return { exitCode: 0, output: `${result.stdout}${result.stderr}` };
  } catch (error) {
    const failure = error as {
      code?: number | string;
      stdout?: string;
      stderr?: string;
    };
    return {
      exitCode: typeof failure.code === "number" ? failure.code : 1,
      output: `${failure.stdout ?? ""}${failure.stderr ?? ""}`,
    };
  }
}

function argumentValue(name: string): string | null {
  const index = process.argv.indexOf(name);
  if (index < 0) return null;
  const value = process.argv[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`${name} requires a value.`);
  }
  return value;
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
});
