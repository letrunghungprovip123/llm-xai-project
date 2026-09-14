import { access, mkdir, readFile, rename, rm } from "node:fs/promises";
import path from "node:path";
import { CLAIM_VALIDATION_MANIFEST_VERSION } from "./constants";

export async function writeNewOutputDirectory<T>(options: {
  outputDirectory: string;
  force: boolean;
  write: (stagingDirectory: string) => Promise<T>;
}): Promise<T> {
  const outputDirectory = path.resolve(options.outputDirectory);
  if (outputDirectory === path.parse(outputDirectory).root) {
    throw new Error("Filesystem root cannot be used as a validation output directory.");
  }
  const stagingDirectory = `${outputDirectory}.tmp-${process.pid}-${Date.now()}`;
  const exists = await pathExists(outputDirectory);
  if (exists && !options.force) {
    throw new Error(
      `Output directory already exists and --force is false: ${outputDirectory}`,
    );
  }
  if (await pathExists(stagingDirectory)) {
    throw new Error(`Staging directory already exists: ${stagingDirectory}`);
  }
  await mkdir(path.dirname(outputDirectory), { recursive: true });
  await mkdir(stagingDirectory);
  try {
    const result = await options.write(stagingDirectory);
    if (exists) {
      await assertReplaceableValidationOutput(outputDirectory);
      await rm(outputDirectory, { recursive: true });
    }
    await rename(stagingDirectory, outputDirectory);
    return result;
  } catch (error) {
    await rm(stagingDirectory, { recursive: true, force: true });
    throw error;
  }
}

async function assertReplaceableValidationOutput(
  outputDirectory: string,
): Promise<void> {
  const manifestPath = path.join(
    outputDirectory,
    "claim_validation_manifest.json",
  );
  let manifest: unknown;
  try {
    manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  } catch {
    throw new Error(
      `--force may replace only a prior claim-validation output: ${outputDirectory}`,
    );
  }
  if (
    typeof manifest !== "object" ||
    manifest === null ||
    !("schema_version" in manifest) ||
    !["claim_validation_manifest_v1", CLAIM_VALIDATION_MANIFEST_VERSION].includes(
      String(manifest.schema_version),
    )
  ) {
    throw new Error(
      `--force target is not a claim-validation output: ${outputDirectory}`,
    );
  }
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}
