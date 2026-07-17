import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { mkdir, readFile, rename, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import readline from "node:readline";

import type {
  ArtifactDescriptor,
  FileProfile,
  JsonObject,
} from "../../../types/llm-validation";

export type JsonlRecord<T> = {
  line: number;
  value: T;
};

export type LoadedJsonl<T> = {
  path: string;
  sha256: string;
  byte_count: number;
  records: JsonlRecord<T>[];
};

export async function readJsonlStrict<T extends JsonObject>(
  filePath: string,
): Promise<LoadedJsonl<T>> {
  const absolutePath = path.resolve(filePath);
  const records: JsonlRecord<T>[] = [];
  const input = createReadStream(absolutePath, { encoding: "utf8" });
  const lines = readline.createInterface({ input, crlfDelay: Infinity });

  let lineNumber = 0;
  for await (const rawLine of lines) {
    lineNumber += 1;
    const line = rawLine.trim();
    if (!line) {
      continue;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(
        `Invalid JSONL at ${absolutePath}, line ${lineNumber}: ${message}`,
      );
    }

    if (!isPlainObject(parsed)) {
      throw new Error(
        `Expected a JSON object at ${absolutePath}, line ${lineNumber}.`,
      );
    }

    records.push({ line: lineNumber, value: parsed as T });
  }

  const fileStat = await stat(absolutePath);
  return {
    path: absolutePath,
    sha256: await sha256File(absolutePath),
    byte_count: fileStat.size,
    records,
  };
}

export async function readJsonStrict<T extends JsonObject>(
  filePath: string,
): Promise<{ path: string; sha256: string; byte_count: number; value: T }> {
  const absolutePath = path.resolve(filePath);
  const text = await readFile(absolutePath, "utf8");
  let parsed: unknown;

  try {
    parsed = JSON.parse(text);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Invalid JSON at ${absolutePath}: ${message}`);
  }

  if (!isPlainObject(parsed)) {
    throw new Error(`Expected a JSON object at ${absolutePath}.`);
  }

  const fileStat = await stat(absolutePath);
  return {
    path: absolutePath,
    sha256: await sha256File(absolutePath),
    byte_count: fileStat.size,
    value: parsed as T,
  };
}

export async function readCsvStrict(filePath: string): Promise<{
  path: string;
  sha256: string;
  byte_count: number;
  headers: string[];
  rows: Record<string, string>[];
}> {
  const absolutePath = path.resolve(filePath);
  const text = await readFile(absolutePath, "utf8");
  const parsedRows = parseCsv(text);

  if (parsedRows.length === 0) {
    throw new Error(`CSV is empty: ${absolutePath}`);
  }

  const headers = parsedRows[0];
  if (headers.length === 0 || headers.some((header) => !header.trim())) {
    throw new Error(`CSV has an empty header at ${absolutePath}.`);
  }

  const rows = parsedRows.slice(1).map((values, index) => {
    if (values.length !== headers.length) {
      throw new Error(
        `Ragged CSV at ${absolutePath}, row ${index + 2}: expected ${headers.length} columns, found ${values.length}.`,
      );
    }

    return Object.fromEntries(headers.map((header, column) => [header, values[column]]));
  });

  const fileStat = await stat(absolutePath);
  return {
    path: absolutePath,
    sha256: await sha256File(absolutePath),
    byte_count: fileStat.size,
    headers,
    rows,
  };
}

export async function writeJsonlAtomic(
  filePath: string,
  records: unknown[],
): Promise<ArtifactDescriptor> {
  const content = records.map((record) => JSON.stringify(record)).join("\n");
  await writeTextAtomic(filePath, content ? `${content}\n` : "");
  return describeArtifact(filePath, records.length);
}

export async function writeJsonAtomic(
  filePath: string,
  value: unknown,
): Promise<ArtifactDescriptor> {
  await writeTextAtomic(filePath, `${JSON.stringify(value, null, 2)}\n`);
  return describeArtifact(filePath);
}

export async function writeCsvAtomic(
  filePath: string,
  rows: Record<string, unknown>[],
  explicitHeaders?: string[],
): Promise<ArtifactDescriptor> {
  const headers = explicitHeaders ?? (rows[0] ? Object.keys(rows[0]) : []);
  const lines = [headers.map(csvEscape).join(",")];

  for (const row of rows) {
    lines.push(headers.map((header) => csvEscape(row[header])).join(","));
  }

  await writeTextAtomic(filePath, headers.length > 0 ? `${lines.join("\n")}\n` : "");
  return describeArtifact(filePath, rows.length);
}

export async function writeTextArtifactAtomic(
  filePath: string,
  content: string,
): Promise<ArtifactDescriptor> {
  await writeTextAtomic(filePath, content);
  return describeArtifact(filePath);
}

export async function copyFileVerified(
  sourcePath: string,
  destinationPath: string,
): Promise<ArtifactDescriptor> {
  const source = await readFile(path.resolve(sourcePath));
  await writeBufferAtomic(destinationPath, source);
  const sourceHash = await sha256File(sourcePath);
  const output = await describeArtifact(destinationPath);

  if (sourceHash !== output.sha256) {
    throw new Error(`Copy verification failed for ${destinationPath}.`);
  }

  return output;
}

export async function describeArtifact(
  filePath: string,
  recordCount?: number,
): Promise<ArtifactDescriptor> {
  const absolutePath = path.resolve(filePath);
  const fileStat = await stat(absolutePath);
  return {
    path: absolutePath,
    sha256: await sha256File(absolutePath),
    byte_count: fileStat.size,
    ...(recordCount === undefined ? {} : { record_count: recordCount }),
  };
}

export async function sha256File(filePath: string): Promise<string> {
  const hash = createHash("sha256");
  const input = createReadStream(path.resolve(filePath));

  for await (const chunk of input) {
    hash.update(chunk as Buffer);
  }

  return hash.digest("hex");
}

export function profileJsonl<T extends JsonObject>(
  loaded: LoadedJsonl<T>,
): FileProfile {
  const fields: NonNullable<FileProfile["top_level_fields"]> = {};

  for (const { value } of loaded.records) {
    for (const [key, item] of Object.entries(value)) {
      const profile = (fields[key] ??= {
        present_count: 0,
        null_count: 0,
        types: {},
      });
      profile.present_count += 1;
      if (item === null) {
        profile.null_count += 1;
      }
      const type = jsonType(item);
      profile.types[type] = (profile.types[type] ?? 0) + 1;
    }
  }

  return {
    path: loaded.path,
    sha256: loaded.sha256,
    byte_count: loaded.byte_count,
    format: "jsonl",
    record_count: loaded.records.length,
    invalid_record_count: 0,
    top_level_fields: fields,
  };
}

export function profileJson(input: {
  path: string;
  sha256: string;
  byte_count: number;
  value: JsonObject;
}): FileProfile {
  const fields: NonNullable<FileProfile["top_level_fields"]> = {};
  for (const [key, value] of Object.entries(input.value)) {
    fields[key] = {
      present_count: 1,
      null_count: value === null ? 1 : 0,
      types: { [jsonType(value)]: 1 },
    };
  }

  return {
    path: input.path,
    sha256: input.sha256,
    byte_count: input.byte_count,
    format: "json",
    record_count: 1,
    invalid_record_count: 0,
    top_level_fields: fields,
  };
}

export function profileCsv(input: {
  path: string;
  sha256: string;
  byte_count: number;
  headers: string[];
  rows: Record<string, string>[];
}): FileProfile {
  return {
    path: input.path,
    sha256: input.sha256,
    byte_count: input.byte_count,
    format: "csv",
    record_count: input.rows.length,
    invalid_record_count: 0,
    csv_headers: input.headers,
    csv_widths: { [String(input.headers.length)]: input.rows.length + 1 },
  };
}

async function writeTextAtomic(filePath: string, content: string): Promise<void> {
  await writeBufferAtomic(filePath, Buffer.from(content, "utf8"));
}

async function writeBufferAtomic(filePath: string, content: Buffer): Promise<void> {
  const absolutePath = path.resolve(filePath);
  await mkdir(path.dirname(absolutePath), { recursive: true });
  const temporaryPath = `${absolutePath}.tmp-${process.pid}-${Date.now()}`;
  await writeFile(temporaryPath, content);
  await rename(temporaryPath, absolutePath);
}

function csvEscape(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];

    if (inQuotes) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') {
        inQuotes = false;
      } else {
        field += character;
      }
      continue;
    }

    if (character === '"') {
      inQuotes = true;
    } else if (character === ",") {
      row.push(field);
      field = "";
    } else if (character === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += character;
    }
  }

  if (inQuotes) {
    throw new Error("CSV ended inside a quoted field.");
  }

  if (field || row.length > 0) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }

  return rows;
}

function jsonType(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

export function isPlainObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
