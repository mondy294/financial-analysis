import fs from "node:fs";
import path from "node:path";

type DotEnvMap = Record<string, string>;

let cachedDotEnv: DotEnvMap | null = null;

function stripWrappingQuotes(value: string) {
  const trimmed = value.trim();
  if ((trimmed.startsWith("\"") && trimmed.endsWith("\"")) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function readDotEnvFile(): DotEnvMap {
  if (cachedDotEnv) {
    return cachedDotEnv;
  }

  const envFilePath = path.resolve(process.cwd(), ".env");
  if (!fs.existsSync(envFilePath)) {
    cachedDotEnv = {};
    return cachedDotEnv;
  }

  const content = fs.readFileSync(envFilePath, "utf-8");
  const result: DotEnvMap = {};

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const delimiterIndex = line.indexOf("=");
    if (delimiterIndex <= 0) {
      continue;
    }

    const key = line.slice(0, delimiterIndex).trim();
    const value = stripWrappingQuotes(line.slice(delimiterIndex + 1));

    if (key) {
      result[key] = value;
    }
  }

  cachedDotEnv = result;
  return result;
}

export function getEnvValue(keys: string[], fallback?: string | null) {
  const dotEnv = readDotEnvFile();

  for (const key of keys) {
    const processValue = process.env[key];
    if (typeof processValue === "string" && processValue.trim()) {
      return processValue.trim();
    }

    const dotEnvValue = dotEnv[key];
    if (typeof dotEnvValue === "string" && dotEnvValue.trim()) {
      return dotEnvValue.trim();
    }
  }

  return fallback ?? null;
}

export function getRequiredEnvValue(keys: string[], errorMessage: string) {
  const value = getEnvValue(keys);
  if (!value) {
    throw new Error(errorMessage);
  }
  return value;
}
