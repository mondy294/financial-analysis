import { getFundAgentReports, getWatchlist, saveFundAgentReports } from "../data-store.js";
import type {
  FundAgentBatchAnalysisItem,
  FundAgentBatchAnalysisResult,
  PersistedFundAgentAnalysis,
} from "../types.js";
import { FundAgentService } from "./fund-agent-service.js";

const DEFAULT_BATCH_HORIZON = "未来 1-3 个月";

function normalizeFundCode(code: string) {
  const cleanCode = String(code || "").trim();
  if (!/^\d{6}$/.test(cleanCode)) {
    throw new Error("基金编号必须是 6 位数字。");
  }
  return cleanCode;
}

function toErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "请求失败，请稍后再试。";
}

function normalizeOptionalText(value: string | null | undefined) {
  const text = String(value ?? "").trim();
  return text.length > 0 ? text : null;
}

function normalizeOptionalCodes(codes?: string[] | null) {
  if (!Array.isArray(codes)) {
    return null;
  }

  const seen = new Set<string>();
  const result: string[] = [];

  codes.forEach((code) => {
    const normalized = normalizeFundCode(code);
    if (seen.has(normalized)) {
      return;
    }
    seen.add(normalized);
    result.push(normalized);
  });

  return result;
}

async function resolveWatchlistCodes(codes?: string[] | null) {
  const normalizedCodes = normalizeOptionalCodes(codes);
  if (normalizedCodes) {
    return normalizedCodes;
  }

  const payload = await getWatchlist();
  const seen = new Set<string>();

  return payload.items
    .map((item) => normalizeFundCode(item.code))
    .filter((code) => {
      if (seen.has(code)) {
        return false;
      }
      seen.add(code);
      return true;
    });
}

function toPersistedFundAgentAnalysis(record: Awaited<ReturnType<FundAgentService["analyzeFund"]>>): PersistedFundAgentAnalysis {
  return {
    ...record,
    updatedAt: record.generatedAt,
  };
}

export async function persistFundAgentAnalysis(record: PersistedFundAgentAnalysis) {
  const payload = await getFundAgentReports();
  const nextItems = payload.items.filter((item) => item.fundCode !== record.fundCode);
  nextItems.unshift(record);
  await saveFundAgentReports(nextItems);
}

export async function analyzeFundAndPersist(
  service: FundAgentService,
  input: {
    fundCode: string;
    horizon?: string | null;
    userQuestion?: string | null;
  },
) {
  const payload = await service.analyzeFund({
    fundCode: normalizeFundCode(input.fundCode),
    horizon: normalizeOptionalText(input.horizon),
    userQuestion: normalizeOptionalText(input.userQuestion),
  });
  const record = toPersistedFundAgentAnalysis(payload);
  await persistFundAgentAnalysis(record);
  return record;
}

export async function analyzeWatchlistFundsAndPersist(input?: {
  service?: FundAgentService;
  codes?: string[] | null;
  horizon?: string | null;
  userQuestion?: string | null;
}): Promise<FundAgentBatchAnalysisResult> {
  const service = input?.service ?? new FundAgentService();
  const horizon = normalizeOptionalText(input?.horizon) ?? DEFAULT_BATCH_HORIZON;
  const userQuestion = normalizeOptionalText(input?.userQuestion);
  const codes = await resolveWatchlistCodes(input?.codes);
  const startedAt = new Date().toISOString();
  const items: FundAgentBatchAnalysisItem[] = [];

  for (const fundCode of codes) {
    try {
      const record = await analyzeFundAndPersist(service, {
        fundCode,
        horizon,
        userQuestion,
      });

      items.push({
        fundCode,
        fundName: record.fundName,
        status: "success",
        generatedAt: record.generatedAt,
        updatedAt: record.updatedAt,
        error: null,
      });
    } catch (error) {
      items.push({
        fundCode,
        fundName: null,
        status: "failed",
        generatedAt: null,
        updatedAt: null,
        error: toErrorMessage(error),
      });
    }
  }

  const finishedAt = new Date().toISOString();
  const succeeded = items.filter((item) => item.status === "success").length;
  const failed = items.length - succeeded;

  return {
    scope: "watchlist",
    horizon,
    userQuestion,
    total: items.length,
    succeeded,
    failed,
    startedAt,
    finishedAt,
    durationMs: new Date(finishedAt).getTime() - new Date(startedAt).getTime(),
    items,
  };
}
