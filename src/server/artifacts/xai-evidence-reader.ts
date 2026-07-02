import { readJsonArtifact } from "./artifact-loader";

export async function readXaiEvidence(customerId: string) {
  return readJsonArtifact(`artifacts/xai-evidence/${customerId}.json`);
}
