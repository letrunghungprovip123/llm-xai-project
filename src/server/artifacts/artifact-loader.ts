import fs from "fs/promises";
import path from "path";

export async function readJsonArtifact<T>(
  relativePath: string,
): Promise<T | null> {
  try {
    const fullPath = path.join(process.cwd(), relativePath);
    const raw = await fs.readFile(fullPath, "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export async function writeJsonArtifact(relativePath: string, data: unknown) {
  const fullPath = path.join(process.cwd(), relativePath);
  await fs.mkdir(path.dirname(fullPath), { recursive: true });
  await fs.writeFile(fullPath, JSON.stringify(data, null, 2), "utf-8");
}
