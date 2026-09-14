import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { evaluateCalibration } from "../../../research/ts/claim_validation/calibration/evaluate";
import {
  classificationReport,
  cohensKappa,
  rawAgreement,
} from "../../../research/ts/claim_validation/calibration/metrics";
import {
  csvCell,
  parseCsv,
  stableBlindId,
} from "../../../research/ts/claim_validation/calibration/io";

test("calibration metrics compute exact agreement and per-status errors", () => {
  const human = [
    "SUPPORTED",
    "UNSUPPORTED",
    "CONTRADICTED",
    "NOT_VERIFIABLE",
  ] as const;
  assert.equal(rawAgreement(human, human), 1);
  assert.equal(cohensKappa(human, human), 1);
  const report = classificationReport(human, [
    "SUPPORTED",
    "SUPPORTED",
    "CONTRADICTED",
    "NOT_VERIFIABLE",
  ]);
  assert.equal(report.per_status.SUPPORTED.precision, 0.5);
  assert.equal(report.per_status.UNSUPPORTED.recall, 0);
  assert.equal(report.false_accept_rate, 1 / 3);
  assert.equal(report.false_reject_rate, 0);
  assert.throws(
    () => rawAgreement(["SUPPORTED"], []),
    /length mismatch/u,
  );
  assert.equal(cohensKappa([], []), 0);
  assert.equal(cohensKappa(["SUPPORTED"], ["SUPPORTED"]), 1);
  assert.equal(csvCell('a"b'), '"a""b"');
  assert.deepEqual(parseCsv('"a","b"\n"1","x""y"\n'), [
    { a: "1", b: 'x"y' },
  ]);
  assert.throws(() => parseCsv('"unterminated'), /Unterminated quoted/u);
  assert.equal(stableBlindId("claim_1"), stableBlindId("claim_1"));
});

test("blank real-rating templates produce an explicit C6 failure", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "claim-calibration-"));
  const packageDirectory = path.join(root, "package");
  const outputPath = path.join(root, "report.json");
  const template =
    '"blind_id","rater_id","claim_type_correct","claim_complete","evidence_identity_correct","validation_status","reason_family","critical_ambiguity","notes"\n'
    + '"blind_1","","","","","","","",""\n';
  try {
    await import("node:fs/promises").then(({ mkdir }) =>
      mkdir(packageDirectory, { recursive: true }),
    );
    await Promise.all([
      writeFile(
        path.join(packageDirectory, "validator_reference.jsonl"),
        `${JSON.stringify({
          blind_id: "blind_1",
          claim_id: "claim_1",
        })}\n`,
      ),
      writeFile(
        path.join(root, "results.jsonl"),
        `${JSON.stringify({
          claim_id: "claim_1",
          model_id: "blinded_model",
          evidence_level: "S1",
          claim_type: "prediction",
          claim_subtype: "OVERALL_LABEL",
          validation_status: "SUPPORTED",
          reason_code: "EXACT_MATCH",
        })}\n`,
      ),
      writeFile(
        path.join(packageDirectory, "blinding_manifest.json"),
        JSON.stringify({ source_results_path: path.join(root, "results.jsonl") }),
      ),
      writeFile(path.join(root, "a.csv"), template),
      writeFile(path.join(root, "b.csv"), template),
    ]);
    const report = await evaluateCalibration({
      packageDirectory,
      raterAPath: path.join(root, "a.csv"),
      raterBPath: path.join(root, "b.csv"),
      outputPath,
    });
    assert.equal(report.c6_pass, false);
    assert.equal(report.double_rated_count, 0);
    assert.match(await readFile(outputPath, "utf8"), /INCOMPLETE_OR_FAIL/u);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("completed ratings compute agreement, adjudication and grouped metrics", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "claim-calibration-full-"));
  const packageDirectory = path.join(root, "package");
  const statuses = [
    "SUPPORTED",
    "UNSUPPORTED",
    "CONTRADICTED",
    "NOT_VERIFIABLE",
  ] as const;
  try {
    await import("node:fs/promises").then(({ mkdir }) =>
      mkdir(packageDirectory, { recursive: true }),
    );
    const references = statuses.map((_, index) => ({
      blind_id: `blind_${index}`,
      claim_id: `claim_${index}`,
    }));
    const results = statuses.map((status, index) => ({
      claim_id: `claim_${index}`,
      model_id: `model_${index % 2}`,
      evidence_level: `S${index}`,
      claim_type: index === 0 ? "prediction" : "feature_presence",
      claim_subtype: index === 0 ? "OVERALL_LABEL" : "FEATURE_IDENTITY",
      validation_status: status,
      reason_code:
        status === "SUPPORTED"
          ? "EXACT_MATCH"
          : status === "UNSUPPORTED"
            ? "FEATURE_NOT_FOUND_IN_EVIDENCE"
            : status === "CONTRADICTED"
              ? "PREDICTION_LABEL_MISMATCH"
              : "PREDICTION_VALUE_UNAVAILABLE",
    }));
    const csv = (values: readonly string[], rater: string) =>
      '"blind_id","rater_id","claim_type_correct","claim_complete","evidence_identity_correct","validation_status","reason_family","critical_ambiguity","notes"\n'
      + values
        .map(
          (status, index) =>
            `"blind_${index}","${rater}","true","true","true","${status}","MATCH","false",""`,
        )
        .join("\n")
      + "\n";
    const raterB = [...statuses];
    raterB[1] = "SUPPORTED";
    await Promise.all([
      writeFile(
        path.join(packageDirectory, "validator_reference.jsonl"),
        references.map((value) => JSON.stringify(value)).join("\n") + "\n",
      ),
      writeFile(
        path.join(packageDirectory, "blinding_manifest.json"),
        JSON.stringify({ source_results_path: path.join(root, "results.jsonl") }),
      ),
      writeFile(
        path.join(root, "results.jsonl"),
        results.map((value) => JSON.stringify(value)).join("\n") + "\n",
      ),
      writeFile(path.join(root, "a.csv"), csv(statuses, "rater_a")),
      writeFile(path.join(root, "b.csv"), csv(raterB, "rater_b")),
      writeFile(
        path.join(root, "adjudication.csv"),
        csv(["SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "NOT_VERIFIABLE"], "adjudicator"),
      ),
    ]);
    const report = await evaluateCalibration({
      packageDirectory,
      raterAPath: path.join(root, "a.csv"),
      raterBPath: path.join(root, "b.csv"),
      adjudicationPath: path.join(root, "adjudication.csv"),
      outputPath: path.join(root, "report.json"),
    });
    assert.equal(report.double_rated_count, 4);
    assert.equal(report.disagreement_count, 1);
    assert.equal(report.unresolved_disagreement_count, 0);
    assert.deepEqual(
      (report.validator_vs_human as { macro_f1: number }).macro_f1,
      1,
    );
    assert.equal(
      Object.keys(report.breakdowns as Record<string, unknown>).length,
      4,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("calibration importer rejects invalid or unattributed human labels", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "claim-calibration-bad-"));
  const packageDirectory = path.join(root, "package");
  try {
    await import("node:fs/promises").then(({ mkdir }) =>
      mkdir(packageDirectory, { recursive: true }),
    );
    await Promise.all([
      writeFile(
        path.join(packageDirectory, "validator_reference.jsonl"),
        '{"blind_id":"blind_1","claim_id":"claim_1"}\n',
      ),
      writeFile(
        path.join(packageDirectory, "blinding_manifest.json"),
        JSON.stringify({ source_results_path: path.join(root, "results.jsonl") }),
      ),
      writeFile(
        path.join(root, "results.jsonl"),
        '{"claim_id":"claim_1","model_id":"m","evidence_level":"S1","claim_type":"prediction","claim_subtype":"OVERALL_LABEL","validation_status":"SUPPORTED","reason_code":"EXACT_MATCH"}\n',
      ),
    ]);
    const writeRating = async (status: string, rater: string) => {
      const content =
        '"blind_id","rater_id","validation_status"\n'
        + `"blind_1","${rater}","${status}"\n`;
      await Promise.all([
        writeFile(path.join(root, "a.csv"), content),
        writeFile(path.join(root, "b.csv"), content),
      ]);
    };
    await writeRating("INVALID", "rater");
    await assert.rejects(
      evaluateCalibration({
        packageDirectory,
        raterAPath: path.join(root, "a.csv"),
        raterBPath: path.join(root, "b.csv"),
        outputPath: path.join(root, "report.json"),
      }),
      /Invalid human validation status/u,
    );
    await writeRating("SUPPORTED", "");
    await assert.rejects(
      evaluateCalibration({
        packageDirectory,
        raterAPath: path.join(root, "a.csv"),
        raterBPath: path.join(root, "b.csv"),
        outputPath: path.join(root, "report.json"),
      }),
      /Missing pseudonymous rater_id/u,
    );
    await writeFile(
      path.join(packageDirectory, "validator_reference.jsonl"),
      '{"blind_id":"blind_missing","claim_id":"claim_missing"}\n',
    );
    await writeRating("SUPPORTED", "rater");
    await assert.rejects(
      evaluateCalibration({
        packageDirectory,
        raterAPath: path.join(root, "a.csv"),
        raterBPath: path.join(root, "b.csv"),
        outputPath: path.join(root, "report.json"),
      }),
      /Missing validator result/u,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
