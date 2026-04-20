import { getEnvValue } from "./env.js";
import { getModelProviderSettings, saveModelProviderSettings } from "./data-store.js";
import type { ModelProviderSettingsResponse, ModelProviderSettingsUpdate } from "./types.js";

const DEFAULT_BASE_URL = getEnvValue(["DEEPSEEK_BASE_URL"], "https://api.deepseek.com") || "https://api.deepseek.com";
const DEFAULT_MODEL = getEnvValue(["DEEPSEEK_MODEL"], "deepseek-reasoner") || "deepseek-reasoner";

function maskApiKey(value: string | null) {
  if (!value) {
    return null;
  }

  if (value.length <= 8) {
    return `${value.slice(0, 2)}****`;
  }

  return `${value.slice(0, 4)}****${value.slice(-4)}`;
}

export async function getModelProviderSettingsResponse(): Promise<ModelProviderSettingsResponse> {
  const persisted = await getModelProviderSettings();
  const envApiKey = getEnvValue(["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "api_key"]);
  const envBaseUrl = getEnvValue(["DEEPSEEK_BASE_URL"]);
  const effectiveApiKey = persisted.apiKey || envApiKey || null;
  const effectiveBaseUrl = persisted.baseUrl || envBaseUrl || DEFAULT_BASE_URL;

  return {
    baseUrl: effectiveBaseUrl,
    model: DEFAULT_MODEL,
    apiKeyConfigured: Boolean(effectiveApiKey),
    apiKeyMasked: maskApiKey(effectiveApiKey),
    hasCustomBaseUrl: Boolean(persisted.baseUrl),
    hasCustomApiKey: Boolean(persisted.apiKey),
  };
}

export async function updateModelProviderSettings(input: ModelProviderSettingsUpdate): Promise<ModelProviderSettingsResponse> {
  await saveModelProviderSettings(input);
  return getModelProviderSettingsResponse();
}

export async function resolveModelProviderRuntimeConfig() {
  const persisted = await getModelProviderSettings();
  const apiKey = persisted.apiKey || getEnvValue(["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "api_key"]);
  const baseUrl = persisted.baseUrl || getEnvValue(["DEEPSEEK_BASE_URL"], DEFAULT_BASE_URL) || DEFAULT_BASE_URL;

  if (!apiKey) {
    throw new Error("缺少大模型 API Key，请先在设置页或 .env 中配置。");
  }

  return {
    apiKey,
    baseUrl,
    model: DEFAULT_MODEL,
  };
}
