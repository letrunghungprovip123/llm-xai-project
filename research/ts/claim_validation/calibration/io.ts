import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

export async function readJsonl<T>(filePath: string): Promise<T[]> {
  const content = await readFile(filePath, "utf8");
  return content
    .split(/\r?\n/u)
    .filter((line) => line.trim().length > 0)
    .map((line, index) => {
      try {
        return JSON.parse(line) as T;
      } catch {
        throw new Error(`Invalid JSONL at ${filePath}:${index + 1}.`);
      }
    });
}

export function stableBlindId(value: string): string {
  return `blind_${createHash("sha256").update(value).digest("hex").slice(0, 20)}`;
}

export function csvCell(value: string): string {
  return `"${value.replaceAll('"', '""')}"`;
}

export function parseCsv(content: string): Record<string, string>[] {
  const rows = parseCsvRows(content);
  const header = rows.shift();
  if (!header) return [];
  return rows
    .filter((row) => row.some((cell) => cell.length > 0))
    .map((row) =>
      Object.fromEntries(header.map((name, index) => [name, row[index] ?? ""])),
    );
}

function parseCsvRows(content: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < content.length; index += 1) {
    const character = content[index];
    if (character === '"') {
      if (quoted && content[index + 1] === '"') {
        value += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === "," && !quoted) {
      row.push(value);
      value = "";
    } else if ((character === "\n" || character === "\r") && !quoted) {
      if (character === "\r" && content[index + 1] === "\n") index += 1;
      row.push(value);
      rows.push(row);
      row = [];
      value = "";
    } else {
      value += character;
    }
  }
  if (value.length > 0 || row.length > 0) {
    row.push(value);
    rows.push(row);
  }
  if (quoted) throw new Error("Unterminated quoted CSV field.");
  return rows;
}
