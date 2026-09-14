import {
  EVIDENCE_LEVELS,
  type EvidenceLevel,
} from "../../../contracts/llm-validation";
import type { ExposedDirection } from "./runtimeTypes";

const evidenceLevels = new Set<string>(EVIDENCE_LEVELS);
const exposedDirections = new Set<string>([
  "increases_risk",
  "decreases_risk",
  "increase_risk",
  "decrease_risk",
  "mixed",
  "neutral",
  "unknown",
]);

export function requireObject(
  value: unknown,
  context: string,
): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new Error(`${context} must be an object.`);
  }
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function requireString(
  value: unknown,
  context: string,
): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${context} must be a non-empty string.`);
  }
  return value;
}

export function optionalString(
  value: unknown,
  context: string,
): string | undefined {
  if (value === undefined) return undefined;
  return requireString(value, context);
}

export function requireBoolean(
  value: unknown,
  context: string,
): boolean {
  if (typeof value !== "boolean") {
    throw new Error(`${context} must be a boolean.`);
  }
  return value;
}

export function optionalBoolean(
  value: unknown,
  context: string,
): boolean | undefined {
  if (value === undefined) return undefined;
  return requireBoolean(value, context);
}

export function requireFiniteNumber(
  value: unknown,
  context: string,
): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${context} must be a finite number.`);
  }
  return value;
}

export function optionalFiniteNumber(
  value: unknown,
  context: string,
): number | undefined {
  if (value === undefined) return undefined;
  return requireFiniteNumber(value, context);
}

export function requirePositiveInteger(
  value: unknown,
  context: string,
): number {
  const parsed = requireFiniteNumber(value, context);
  if (!Number.isInteger(parsed) || parsed < 1) {
    throw new Error(`${context} must be a positive integer.`);
  }
  return parsed;
}

export function optionalNonNegativeInteger(
  value: unknown,
  context: string,
): number | undefined {
  if (value === undefined) return undefined;
  const parsed = requireFiniteNumber(value, context);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error(`${context} must be a non-negative integer.`);
  }
  return parsed;
}

export function requireStringArray(
  value: unknown,
  context: string,
): string[] {
  if (!Array.isArray(value)) throw new Error(`${context} must be an array.`);
  return value.map((item, index) =>
    requireString(item, `${context}[${index}]`),
  );
}

export function requireEvidenceLevel(
  value: unknown,
  context: string,
): EvidenceLevel {
  const level = requireString(value, context);
  if (!evidenceLevels.has(level)) {
    throw new Error(`${context} has invalid evidence level ${level}.`);
  }
  if (level === "S0") return "S0";
  if (level === "S1") return "S1";
  if (level === "S2") return "S2";
  if (level === "S3") return "S3";
  if (level === "S4") return "S4";
  return "S5";
}

export function requireDirection(
  value: unknown,
  context: string,
): ExposedDirection {
  const direction = requireString(value, context);
  if (!exposedDirections.has(direction)) {
    throw new Error(`${context} has invalid direction ${direction}.`);
  }
  switch (direction) {
    case "increases_risk":
    case "decreases_risk":
    case "increase_risk":
    case "decrease_risk":
    case "mixed":
    case "neutral":
      return direction;
    default:
      return "unknown";
  }
}
