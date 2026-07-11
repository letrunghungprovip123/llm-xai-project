import {
  GetObjectCommand,
  HeadObjectCommand,
  ListObjectsV2Command,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";


let s3Client: S3Client | null = null;


function getS3Client(): S3Client {
  if (!s3Client) {
    s3Client = new S3Client({});
  }

  return s3Client;
}


export function isS3Uri(value: string): boolean {
  return value.startsWith("s3://");
}


export function parseS3Uri(value: string): { bucket: string; key: string } {
  if (!isS3Uri(value)) {
    throw new Error(`Not an S3 URI: ${value}`);
  }

  const withoutPrefix = value.slice("s3://".length);
  const slashIndex = withoutPrefix.indexOf("/");

  if (slashIndex < 0) {
    return {
      bucket: withoutPrefix,
      key: "",
    };
  }

  return {
    bucket: withoutPrefix.slice(0, slashIndex),
    key: withoutPrefix.slice(slashIndex + 1),
  };
}


export function joinPath(base: string, ...parts: string[]): string {
  if (isS3Uri(base)) {
    const cleanBase = base.replace(/\/+$/, "");
    const cleanParts = parts.map((item) => item.replace(/^\/+|\/+$/g, ""));
    return [cleanBase, ...cleanParts].join("/");
  }

  return path.join(base, ...parts);
}


export async function pathExists(pathOrS3Uri: string): Promise<boolean> {
  if (isS3Uri(pathOrS3Uri)) {
    const { bucket, key } = parseS3Uri(pathOrS3Uri);

    try {
      await getS3Client().send(new HeadObjectCommand({
        Bucket: bucket,
        Key: key,
      }));
      return true;
    } catch {
      return false;
    }
  }

  try {
    await stat(pathOrS3Uri);
    return true;
  } catch {
    return false;
  }
}


export async function readTextFile(pathOrS3Uri: string): Promise<string> {
  if (isS3Uri(pathOrS3Uri)) {
    const { bucket, key } = parseS3Uri(pathOrS3Uri);
    const response = await getS3Client().send(new GetObjectCommand({
      Bucket: bucket,
      Key: key,
    }));

    if (!response.Body) {
      throw new Error(`S3 object has no body: ${pathOrS3Uri}`);
    }

    return response.Body.transformToString("utf-8");
  }

  return readFile(pathOrS3Uri, "utf-8");
}


export async function writeTextFile(
  pathOrS3Uri: string,
  content: string,
  contentType = "text/plain; charset=utf-8",
): Promise<void> {
  if (isS3Uri(pathOrS3Uri)) {
    const { bucket, key } = parseS3Uri(pathOrS3Uri);

    await getS3Client().send(new PutObjectCommand({
      Bucket: bucket,
      Key: key,
      Body: content,
      ContentType: contentType,
    }));
    return;
  }

  await mkdir(path.dirname(pathOrS3Uri), { recursive: true });
  await writeFile(pathOrS3Uri, content, "utf-8");
}


export async function writeJsonFile(pathOrS3Uri: string, value: unknown): Promise<void> {
  await writeTextFile(
    pathOrS3Uri,
    JSON.stringify(value, null, 2),
    "application/json; charset=utf-8",
  );
}


export async function writeJsonlFile(pathOrS3Uri: string, records: unknown[]): Promise<void> {
  const lines = records.map((record) => JSON.stringify(record));
  const content = lines.length > 0 ? `${lines.join("\n")}\n` : "";

  await writeTextFile(
    pathOrS3Uri,
    content,
    "application/x-ndjson; charset=utf-8",
  );
}


function escapeCsvValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }

  let text = typeof value === "string" ? value : JSON.stringify(value);
  if (text === undefined) {
    text = String(value);
  }

  if (text.includes(",") || text.includes("\n") || text.includes('"')) {
    return `"${text.replace(/"/g, '""')}"`;
  }

  return text;
}


export async function writeCsvFile(
  pathOrS3Uri: string,
  rows: Record<string, unknown>[],
  fieldNames?: string[],
): Promise<void> {
  const columns = fieldNames || collectFieldNames(rows);
  const lines = [columns.map(escapeCsvValue).join(",")];

  for (const row of rows) {
    lines.push(columns.map((column) => escapeCsvValue(row[column])).join(","));
  }

  await writeTextFile(
    pathOrS3Uri,
    `${lines.join("\n")}\n`,
    "text/csv; charset=utf-8",
  );
}


function collectFieldNames(rows: Record<string, unknown>[]): string[] {
  const result: string[] = [];
  const seen = new Set<string>();

  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!seen.has(key)) {
        seen.add(key);
        result.push(key);
      }
    }
  }

  return result;
}


export async function listFilesRecursive(
  basePath: string,
  fileNameSuffix: string,
): Promise<string[]> {
  if (isS3Uri(basePath)) {
    return listS3Files(basePath, fileNameSuffix);
  }

  const result: string[] = [];

  async function walk(currentPath: string): Promise<void> {
    const entries = await readdir(currentPath, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(currentPath, entry.name);

      if (entry.isDirectory()) {
        await walk(fullPath);
      } else if (entry.isFile() && entry.name.endsWith(fileNameSuffix)) {
        result.push(fullPath);
      }
    }
  }

  if (await pathExists(basePath)) {
    await walk(basePath);
  }

  return result.sort();
}


async function listS3Files(basePath: string, fileNameSuffix: string): Promise<string[]> {
  const { bucket, key } = parseS3Uri(basePath);
  const result: string[] = [];
  let continuationToken: string | undefined;

  do {
    const response = await getS3Client().send(new ListObjectsV2Command({
      Bucket: bucket,
      Prefix: key,
      ContinuationToken: continuationToken,
    }));

    for (const item of response.Contents || []) {
      if (item.Key && item.Key.endsWith(fileNameSuffix)) {
        result.push(`s3://${bucket}/${item.Key}`);
      }
    }

    continuationToken = response.NextContinuationToken;
  } while (continuationToken);

  return result.sort();
}
