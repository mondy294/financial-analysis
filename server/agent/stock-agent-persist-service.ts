import { getStockAgentReports, saveStockAgentReports } from "../data-store.js";
import type { PersistedStockAgentAnalysis } from "../types.js";
import { StockAgentService } from "./stock-agent-service.js";

function normalizeStockCode(code: string) {
  const cleanCode = String(code || "").trim();
  if (!/^\d{6}$/.test(cleanCode)) {
    throw new Error("股票代码必须是 6 位数字。");
  }
  return cleanCode;
}

function normalizeOptionalText(value: string | null | undefined) {
  const text = String(value ?? "").trim();
  return text.length > 0 ? text : null;
}

function toPersistedStockAgentAnalysis(record: Awaited<ReturnType<StockAgentService["analyzeStock"]>>): PersistedStockAgentAnalysis {
  return {
    ...record,
    updatedAt: record.generatedAt,
  };
}

export async function persistStockAgentAnalysis(record: PersistedStockAgentAnalysis) {
  const payload = await getStockAgentReports();
  const nextItems = payload.items.filter((item) => item.stockCode !== record.stockCode);
  nextItems.unshift(record);
  await saveStockAgentReports(nextItems);
}

export async function analyzeStockAndPersist(
  service: StockAgentService,
  input: {
    stockCode: string;
    horizon?: string | null;
    userQuestion?: string | null;
  },
) {
  const payload = await service.analyzeStock({
    stockCode: normalizeStockCode(input.stockCode),
    horizon: normalizeOptionalText(input.horizon),
    userQuestion: normalizeOptionalText(input.userQuestion),
  });

  const record = toPersistedStockAgentAnalysis(payload);
  await persistStockAgentAnalysis(record);
  return record;
}
