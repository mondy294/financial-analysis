import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import OpenAI from "openai";
import { z } from "zod";
import { createFinancialMcpRegistry } from "../mcp/registry.js";
import { resolveModelProviderRuntimeConfig } from "../model-provider-settings-service.js";
import type {
  AgentToolTrace,
  FundMarketNewsQueryResponse,
  FundTradePlanLevel,
  StockAgentAnalysisResponse,
  StockAgentForecast,
  StockAgentForecastPathStyle,
  StockAgentForecastScenario,
  StockAgentForecastVolatility,
  StockAgentReport,
  StockAnalysisResponse,
  StockTradePlanSnapshot,
} from "../types.js";

const DEFAULT_HORIZON = "未来 1-3 个月";
const DEFAULT_ANALYSIS_HISTORY_DAYS = 365;
const DEFAULT_NEWS_LOOKBACK_DAYS = 14;
const DEFAULT_NEWS_LIMIT = 50;
const FORECAST_STEP_DAYS = 7;
const FORECAST_POINT_COUNT = 8;

const planLevelKinds = ["观察确认位", "试探加仓位", "分批加仓位", "减仓位", "风控线"] as const;
const forecastVolatilityLevels = ["低", "中", "高"] as const;
const forecastPathStyles = ["震荡上行", "高位震荡", "区间震荡", "先抑后扬", "先扬后抑", "震荡下行"] as const;

const planLevelSchema = z.object({
  kind: z.enum(planLevelKinds),
  nav: z.number().nullable(),
  relativeToLatest: z.number().nullable(),
  reference: z.string().min(1),
  condition: z.string().min(6),
  action: z.string().min(4),
  reason: z.string().min(4),
});

const agentReportSchema = z.object({
  horizon: z.string().min(1),
  outlook: z.enum(["偏多", "中性", "偏谨慎", "无法判断"]),
  confidence: z.number().int().min(0).max(100),
  recentWeekSummary: z.string().min(8),
  recentWeekDrivers: z.array(z.string().min(4)).min(2).max(6),
  summary: z.string().min(8),
  actionTag: z.enum(["观望为主", "分批布局", "持有待跟踪", "谨慎减仓"]),
  actionAdvice: z.string().min(8),
  holdingContext: z.string().min(6),
  positionInstruction: z.string().min(8),
  positionSizing: z.string().min(4),
  planSummary: z.string().min(8),
  executionRules: z.array(z.string().min(4)).min(3).max(6),
  planLevels: z.array(planLevelSchema).min(3).max(6),
  reEvaluationTriggers: z.array(z.string().min(4)).min(2).max(5),
  suitableFor: z.string().min(4),
  unsuitableFor: z.string().min(4),
  reasoning: z.array(z.string().min(4)).min(3).max(6),
  risks: z.array(z.string().min(4)).min(2).max(5),
  watchItems: z.array(z.string().min(4)).min(2).max(6),
  disclaimer: z.string().min(8),
});

const forecastScenarioSchema = z.object({
  label: z.string().min(2),
  probability: z.number().int().min(0).max(100),
  targetReturn: z.number().min(-45).max(45),
  summary: z.string().min(6),
  trigger: z.string().min(4),
  volatility: z.enum(forecastVolatilityLevels),
  pathStyle: z.enum(forecastPathStyles),
});

type StockAgentRequest = {
  stockCode: string;
  userQuestion?: string | null;
  horizon?: string | null;
};

type PromptAssets = {
  skill: string;
};

let promptAssetsCache: PromptAssets | null = null;

function normalizeStockCode(code: string) {
  const cleanCode = String(code || "").trim();
  if (!/^\d{6}$/.test(cleanCode)) {
    throw new Error("股票代码必须是 6 位数字。");
  }
  return cleanCode;
}

function normalizeInlineText(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

function normalizeNullableNumber(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function roundTo(value: number, digits: number) {
  return Number(value.toFixed(digits));
}

function clampNumber(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function normalizeStringList(value: unknown) {
  if (Array.isArray(value)) {
    return value
      .filter((item): item is string => typeof item === "string")
      .map((item) => normalizeInlineText(item))
      .filter((item) => item.length >= 4)
      .slice(0, 8);
  }

  if (typeof value === "string") {
    return value
      .split(/[\n；;]/)
      .map((item) => normalizeInlineText(item))
      .filter((item) => item.length >= 4)
      .slice(0, 8);
  }

  return [] as string[];
}

function pickText(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim().length > 0 ? normalizeInlineText(value) : fallback;
}

function pickList(value: unknown, fallback: string[], minimum: number, maximum: number) {
  const normalized = normalizeStringList(value);
  const source = normalized.length >= minimum ? normalized : fallback;
  return source.slice(0, maximum);
}

function normalizePlanLevels(value: unknown): FundTradePlanLevel[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => {
      const source = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
      return {
        kind: typeof source.kind === "string" ? source.kind.trim() : "",
        nav: normalizeNullableNumber(source.nav),
        relativeToLatest: normalizeNullableNumber(source.relativeToLatest),
        reference: pickText(source.reference, ""),
        condition: pickText(source.condition, ""),
        action: pickText(source.action, ""),
        reason: pickText(source.reason, ""),
      };
    })
    .filter(
      (item): item is FundTradePlanLevel =>
        (planLevelKinds as readonly string[]).includes(item.kind)
        && Boolean(item.reference)
        && Boolean(item.condition)
        && Boolean(item.action)
        && Boolean(item.reason),
    );
}

function normalizeForecastVolatility(value: unknown): StockAgentForecastVolatility {
  return forecastVolatilityLevels.includes(value as StockAgentForecastVolatility) ? (value as StockAgentForecastVolatility) : "中";
}

function normalizeForecastPathStyle(value: unknown): StockAgentForecastPathStyle {
  return forecastPathStyles.includes(value as StockAgentForecastPathStyle) ? (value as StockAgentForecastPathStyle) : "区间震荡";
}

function normalizeForecastScenarioInputs(value: unknown) {
  if (!Array.isArray(value)) {
    return [] as Array<{
      label: string;
      probability: number;
      targetReturn: number;
      summary: string;
      trigger: string;
      volatility: StockAgentForecastVolatility;
      pathStyle: StockAgentForecastPathStyle;
    }>;
  }

  return value
    .map((item) => {
      const source = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
      return {
        label: pickText(source.label, "情景预测"),
        probability: clampNumber(Math.round(normalizeNullableNumber(source.probability) ?? 0), 0, 100),
        targetReturn: clampNumber(roundTo(normalizeNullableNumber(source.targetReturn) ?? 0, 2), -45, 45),
        summary: pickText(source.summary, "后续路径仍需继续观察。"),
        trigger: pickText(source.trigger, "继续观察关键价位和消息催化。"),
        volatility: normalizeForecastVolatility(source.volatility),
        pathStyle: normalizeForecastPathStyle(source.pathStyle),
      };
    })
    .filter((item) => item.label.length >= 2 && item.summary.length >= 6);
}

function normalizeScenarioProbabilities<T extends { probability: number }>(scenarios: T[]) {
  if (scenarios.length === 0) {
    return scenarios;
  }

  const rawTotal = scenarios.reduce((total, item) => total + item.probability, 0);
  if (rawTotal === 100) {
    return scenarios;
  }

  if (rawTotal <= 0) {
    const even = Math.floor(100 / scenarios.length);
    let remainder = 100 - even * scenarios.length;
    return scenarios.map((item) => {
      const delta = remainder > 0 ? 1 : 0;
      remainder -= delta;
      return { ...item, probability: even + delta };
    });
  }

  const normalized = scenarios.map((item) => ({
    ...item,
    probability: Math.max(1, Math.round((item.probability / rawTotal) * 100)),
  }));
  let drift = 100 - normalized.reduce((total, item) => total + item.probability, 0);

  for (const item of normalized) {
    if (drift === 0) {
      break;
    }
    if (drift > 0) {
      item.probability += 1;
      drift -= 1;
    } else if (item.probability > 1) {
      item.probability -= 1;
      drift += 1;
    }
  }

  return normalized;
}

function easeInOutSine(progress: number) {
  return -(Math.cos(Math.PI * progress) - 1) / 2;
}

function calculateForecastWave(progress: number, amplitude: number, pathStyle: StockAgentForecastPathStyle) {
  const oscillation = Math.sin(progress * Math.PI * 2) * amplitude * 0.45 * (1 - progress * 0.2);
  const swing = Math.sin(progress * Math.PI) * amplitude;

  switch (pathStyle) {
    case "震荡上行":
      return oscillation + swing * 0.18;
    case "高位震荡":
      return oscillation * 0.75 + swing * 0.12;
    case "区间震荡":
      return oscillation * 0.95;
    case "先抑后扬":
      return oscillation * 0.35 - swing * 0.72;
    case "先扬后抑":
      return oscillation * 0.35 + swing * 0.72;
    case "震荡下行":
      return oscillation - swing * 0.18;
    default:
      return oscillation;
  }
}

function shiftDateByDays(dateText: string, days: number) {
  const date = new Date(`${dateText}T00:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function createForecastPoints(input: {
  baseDate: string;
  basePrice: number;
  targetReturn: number;
  volatility: StockAgentForecastVolatility;
  pathStyle: StockAgentForecastPathStyle;
  riskVolatility90d: number | null;
}) {
  const baseAmplitude = clampNumber((input.riskVolatility90d ?? 30) / Math.sqrt(52), 1.5, 12);
  const amplitudeMultiplier = input.volatility === "高" ? 1.05 : input.volatility === "低" ? 0.55 : 0.8;
  const amplitude = baseAmplitude * amplitudeMultiplier;

  return Array.from({ length: FORECAST_POINT_COUNT }, (_, index) => {
    const step = index + 1;
    const progress = step / FORECAST_POINT_COUNT;
    const easedReturn = input.targetReturn * easeInOutSine(progress);
    const wave = step === FORECAST_POINT_COUNT ? 0 : calculateForecastWave(progress, amplitude, input.pathStyle);
    const returnRate = roundTo(easedReturn + wave, 2);
    const price = roundTo(Math.max(0.01, input.basePrice * (1 + returnRate / 100)), 2);

    return {
      date: shiftDateByDays(input.baseDate, step * FORECAST_STEP_DAYS),
      nav: price,
      returnRate,
    };
  });
}

async function loadPromptAssets(): Promise<PromptAssets> {
  if (promptAssetsCache) {
    return promptAssetsCache;
  }

  const skillPath = path.resolve(process.cwd(), "server/agent/skills/stock-trend-analyst/SKILL.md");
  const skill = await fs.readFile(skillPath, "utf-8");
  promptAssetsCache = { skill };
  return promptAssetsCache;
}

function buildSystemPrompt(skill: string) {
  return [
    "你是项目内的股票走势分析 Agent。",
    "你必须优先依据系统提供的股票分析数据、交易计划快照和市场新闻来生成结论。",
    "你必须把开盘价、收盘价、最高价、最低价、振幅、换手率和均线/布林带一起纳入判断。",
    "如果数据证据互相冲突，可以给中性或无法判断，不要硬凑单边结论。",
    "禁止编造财报、订单、政策、资金流细节或任何未给出的数字。",
    "最终只输出合法 JSON，不要输出 Markdown，不要输出代码块。",
    "JSON 顶层必须严格包含这些字段：horizon,outlook,confidence,recentWeekSummary,recentWeekDrivers,summary,actionTag,actionAdvice,holdingContext,positionInstruction,positionSizing,planSummary,executionRules,planLevels,reEvaluationTriggers,suitableFor,unsuitableFor,reasoning,risks,watchItems,disclaimer,forecastScenarios。",
    "actionTag 只能是：观望为主 / 分批布局 / 持有待跟踪 / 谨慎减仓。",
    "outlook 只能是：偏多 / 中性 / 偏谨慎 / 无法判断。",
    "confidence 取 0-100 的整数。",
    "planLevels 必须给出 3-6 个关键价位，至少包含一个试探/加仓相关价位和一个风控线。",
    "forecastScenarios 必须返回 2-4 条，且 probability 合计必须等于 100。",
    "disclaimer 必须明确表达“仅供研究辅助，不构成投资建议”。",
    "以下是你的 Skill：",
    skill,
  ].join("\n\n");
}

function buildUserPrompt(input: { stockCode: string; horizon: string; userQuestion: string }) {
  return [
    `请分析股票 ${input.stockCode}。`,
    `目标周期：${input.horizon}。`,
    input.userQuestion ? `用户补充信息：${input.userQuestion}` : null,
    "请先解释最近一周的 K 线变化和主要扰动，再说明当前结构更接近什么交易状态，最后给出未来 1-3 个月的路径推演。",
    "你必须明确回答：现在更适合观察、试探、分批布局还是谨慎减仓；以及哪些价位更适合加减仓、什么条件出现就要重新评估。",
  ].filter(Boolean).join("\n");
}

function extractTextContent(content: unknown) {
  if (typeof content === "string") {
    return content;
  }

  if (Array.isArray(content)) {
    return content
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (item && typeof item === "object" && "type" in item && (item as { type?: string }).type === "text") {
          return String((item as { text?: string }).text ?? "");
        }
        return "";
      })
      .join("\n")
      .trim();
  }

  return "";
}

function extractJsonBlock(rawText: string) {
  const trimmed = rawText.trim();
  if (!trimmed) {
    throw new Error("模型没有返回股票分析结果。");
  }

  const fencedMatch = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fencedMatch?.[1]) {
    return fencedMatch[1].trim();
  }

  const firstBrace = trimmed.indexOf("{");
  const lastBrace = trimmed.lastIndexOf("}");
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    return trimmed.slice(firstBrace, lastBrace + 1);
  }

  return trimmed;
}

function resolveToolContent(toolOutputs: Map<string, Record<string, unknown> | null>, toolName: string) {
  return toolOutputs.get(toolName) ?? null;
}

function formatShanghaiDateTime(date: Date) {
  const formatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  const parts = formatter.formatToParts(date);
  const mapping = Object.fromEntries(parts.filter((item) => item.type !== "literal").map((item) => [item.type, item.value]));
  return `${mapping.year}-${mapping.month}-${mapping.day} ${mapping.hour}:${mapping.minute}:${mapping.second}`;
}

function buildStockNewsQueryArgs(stockAnalysis: StockAnalysisResponse) {
  const now = new Date();
  const startDate = new Date(now.getTime() - DEFAULT_NEWS_LOOKBACK_DAYS * 24 * 60 * 60 * 1000);
  return {
    startTime: formatShanghaiDateTime(startDate),
    endTime: formatShanghaiDateTime(now),
    regions: ["国内", "海外"] as const,
    topics: ["焦点", "全球股市", "地区", "央行", "经济数据"] as const,
    keywords: [stockAnalysis.stock.name, stockAnalysis.stock.code].filter(Boolean),
    limit: DEFAULT_NEWS_LIMIT,
  };
}

function buildMarketNewsDigest(marketNews: FundMarketNewsQueryResponse | null) {
  if (!marketNews || marketNews.items.length === 0) {
    return "近期没有拿到足够的公开新闻样本，外部催化判断要更保守。";
  }

  const topTopic = marketNews.stats.byTopic.slice().sort((a, b) => b.count - a.count).slice(0, 3).map((item) => `${item.topic}(${item.count})`).join("、");
  const topEvents = marketNews.items.slice(0, 2).map((item) => `《${item.title}》`).join("、");
  return `近 ${DEFAULT_NEWS_LOOKBACK_DAYS} 天纳入 ${marketNews.total} 条相关快讯；主题集中在 ${topTopic || "综合"}${topEvents ? `；高重要度线索包括 ${topEvents}` : ""}`;
}

function buildNewsEvidenceHighlights(marketNews: FundMarketNewsQueryResponse | null) {
  if (!marketNews || marketNews.items.length === 0) {
    return [] as string[];
  }

  const highlights: string[] = [];
  const topTopic = marketNews.stats.byTopic.slice().sort((a, b) => b.count - a.count).slice(0, 3).map((item) => `${item.topic}(${item.count})`).join("、");
  if (topTopic) {
    highlights.push(`近 ${DEFAULT_NEWS_LOOKBACK_DAYS} 天外部扰动主要集中在 ${topTopic}。`);
  }

  const topEvents = marketNews.items.slice(0, 2).map((item) => `《${item.title}》`);
  if (topEvents.length > 0) {
    highlights.push(`高重要度事件包括 ${topEvents.join("、")}。`);
  }

  return highlights.slice(0, 3);
}

function fallbackOutlook(signal: unknown): StockAgentReport["outlook"] {
  if (signal === "多头排列") {
    return "偏多";
  }
  if (signal === "空头排列") {
    return "偏谨慎";
  }
  if (signal === "震荡整理") {
    return "中性";
  }
  return "无法判断";
}

function fallbackActionTag(outlook: StockAgentReport["outlook"]): StockAgentReport["actionTag"] {
  if (outlook === "偏多") {
    return "分批布局";
  }
  if (outlook === "偏谨慎") {
    return "谨慎减仓";
  }
  return "观望为主";
}

function fallbackReasoning(toolOutputs: Map<string, Record<string, unknown> | null>) {
  const stockAnalysis = resolveToolContent(toolOutputs, "get_stock_analysis") as unknown as StockAnalysisResponse | null;
  const tradePlan = resolveToolContent(toolOutputs, "get_stock_trade_plan") as unknown as StockTradePlanSnapshot | null;
  const marketNews = resolveToolContent(toolOutputs, "get_stock_market_news") as unknown as FundMarketNewsQueryResponse | null;
  const latest = stockAnalysis?.trendAnalysis.latest ?? null;
  const returns = stockAnalysis?.trendAnalysis.returns ?? null;

  const reasons: string[] = [];
  if (latest?.signal) {
    reasons.push(`当前趋势结构更接近 ${latest.signal}。`);
  }
  if (typeof latest?.biasToMa20 === "number") {
    reasons.push(`收盘价相对 MA20 乖离约 ${latest.biasToMa20.toFixed(2)}%，可用来判断是否偏离中期中枢。`);
  }
  if (typeof latest?.dailyChangeRate === "number") {
    reasons.push(`最新一根日 K 涨跌幅约 ${latest.dailyChangeRate.toFixed(2)}%，短线强弱已经有了明确方向。`);
  }
  if (typeof latest?.upperShadowRate === "number" && latest.upperShadowRate >= 2) {
    reasons.push(`最新 K 线上影约 ${latest.upperShadowRate.toFixed(2)}%，说明上方仍有抛压。`);
  }
  if (typeof returns?.day60 === "number") {
    reasons.push(`近 60 个交易日涨跌幅约 ${returns.day60.toFixed(2)}%，能帮助判断当前更像修复还是延续。`);
  }
  reasons.push(...normalizeStringList(tradePlan?.riskFlags));
  reasons.push(...buildNewsEvidenceHighlights(marketNews));

  return reasons.slice(0, 6);
}

function fallbackExecutionRules(toolOutputs: Map<string, Record<string, unknown> | null>) {
  const tradePlan = resolveToolContent(toolOutputs, "get_stock_trade_plan") as unknown as StockTradePlanSnapshot | null;
  return (tradePlan?.planLevels ?? []).map((level) => `${level.condition}；执行：${level.action}`).slice(0, 6);
}

function buildPreparedToolContext(input: {
  horizon: string;
  stockAnalysis: StockAnalysisResponse;
  tradePlan: StockTradePlanSnapshot;
  marketNews: FundMarketNewsQueryResponse | null;
}) {
  const latest = input.stockAnalysis.trendAnalysis.latest;
  return {
    analysisHorizon: input.horizon,
    preparedAt: new Date().toISOString(),
    stockContext: {
      code: input.stockAnalysis.stock.code,
      name: input.stockAnalysis.stock.name,
      exchange: input.stockAnalysis.stock.exchange,
      latestTradeDate: input.stockAnalysis.stock.latestTradeDate,
      latestPrice: input.stockAnalysis.stock.latestPrice,
      openPrice: input.stockAnalysis.stock.openPrice,
      highPrice: input.stockAnalysis.stock.highPrice,
      lowPrice: input.stockAnalysis.stock.lowPrice,
      previousClose: input.stockAnalysis.stock.previousClose,
      changeRate: input.stockAnalysis.stock.changeRate,
      changeAmount: input.stockAnalysis.stock.changeAmount,
      turnoverRate: input.stockAnalysis.stock.turnoverRate,
      amplitude: input.stockAnalysis.stock.amplitude,
    },
    recentTrend: {
      signal: latest.signal,
      ma5: latest.ma5,
      ma10: latest.ma10,
      ma20: latest.ma20,
      ma60: latest.ma60,
      biasToMa10: latest.biasToMa10,
      biasToMa20: latest.biasToMa20,
      biasToMa60: latest.biasToMa60,
      bollUpper: latest.bollUpper,
      bollLower: latest.bollLower,
      bollWidth20: latest.bollWidth20,
      open: latest.open,
      close: latest.close,
      high: latest.high,
      low: latest.low,
      dailyChangeRate: latest.dailyChangeRate,
      bodyChangeRate: latest.bodyChangeRate,
      upperShadowRate: latest.upperShadowRate,
      lowerShadowRate: latest.lowerShadowRate,
      amplitude: latest.amplitude,
      turnoverRate: latest.turnoverRate,
    },
    mediumLongTermTrend: {
      return5d: input.stockAnalysis.trendAnalysis.returns.day5,
      return20d: input.stockAnalysis.trendAnalysis.returns.day20,
      return60d: input.stockAnalysis.trendAnalysis.returns.day60,
      return120d: input.stockAnalysis.trendAnalysis.returns.day120,
      return250d: input.stockAnalysis.trendAnalysis.returns.day250,
      maxDrawdown30d: input.stockAnalysis.trendAnalysis.risk.maxDrawdown30d,
      maxDrawdown90d: input.stockAnalysis.trendAnalysis.risk.maxDrawdown90d,
      maxDrawdown1y: input.stockAnalysis.trendAnalysis.risk.maxDrawdown1y,
      volatility30d: input.stockAnalysis.trendAnalysis.risk.volatility30d,
      volatility90d: input.stockAnalysis.trendAnalysis.risk.volatility90d,
      volatility1y: input.stockAnalysis.trendAnalysis.risk.volatility1y,
    },
    performance: input.stockAnalysis.performance,
    tradePlan: input.tradePlan,
    marketNewsSummary: buildMarketNewsDigest(input.marketNews),
  };
}

function finalizeReport(rawReport: unknown, toolOutputs: Map<string, Record<string, unknown> | null>, horizon: string) {
  const source = rawReport && typeof rawReport === "object" ? (rawReport as Record<string, unknown>) : {};
  const stockAnalysis = resolveToolContent(toolOutputs, "get_stock_analysis") as unknown as StockAnalysisResponse | null;
  const tradePlan = resolveToolContent(toolOutputs, "get_stock_trade_plan") as unknown as StockTradePlanSnapshot | null;
  const latest = stockAnalysis?.trendAnalysis.latest ?? null;
  const observationSignals = normalizeStringList(tradePlan?.observationSignals);
  const riskFlags = normalizeStringList(tradePlan?.riskFlags);
  const reasoningFallback = fallbackReasoning(toolOutputs);
  const executionFallback = fallbackExecutionRules(toolOutputs);
  const fallbackPlanLevels = (tradePlan?.planLevels ?? []).slice(0, 6);
  const outlook = (["偏多", "中性", "偏谨慎", "无法判断"] as const).includes(source.outlook as StockAgentReport["outlook"])
    ? (source.outlook as StockAgentReport["outlook"])
    : fallbackOutlook(latest?.signal);
  const actionTag = (["观望为主", "分批布局", "持有待跟踪", "谨慎减仓"] as const).includes(source.actionTag as StockAgentReport["actionTag"])
    ? (source.actionTag as StockAgentReport["actionTag"])
    : fallbackActionTag(outlook);

  const report = {
    horizon: pickText(source.horizon, horizon),
    outlook,
    confidence: clampNumber(Math.round(normalizeNullableNumber(source.confidence) ?? 64), 0, 100),
    recentWeekSummary: pickText(source.recentWeekSummary, pickText(source.summary, "最近一周走势仍在围绕关键均线和 K 线结构做确认。")),
    recentWeekDrivers: pickList(source.recentWeekDrivers, reasoningFallback, 2, 6),
    summary: pickText(source.summary, "当前结论需要结合 K 线结构、均线位置和外部扰动一起看。"),
    actionTag,
    actionAdvice: pickText(source.actionAdvice, tradePlan?.sizingSuggestion.currentActionBias ?? "当前先按小步试探和关键位观察处理。"),
    holdingContext: pickText(source.holdingContext, "当前没有接入本地股票持仓记录，建议按独立标的的试探仓逻辑处理。"),
    positionInstruction: pickText(source.positionInstruction, tradePlan?.sizingSuggestion.currentActionBias ?? "先看关键位是否被确认，再决定是否放大动作。"),
    positionSizing: pickText(source.positionSizing, tradePlan?.sizingSuggestion.initialProbe ?? "先用小仓位试探，不要一次性重仓。"),
    planSummary: pickText(source.planSummary, tradePlan?.sizingSuggestion.currentActionBias ?? "当前以关键价位观察和小步动作为主。"),
    executionRules: pickList(source.executionRules, executionFallback, 3, 6),
    planLevels: normalizePlanLevels(source.planLevels).length >= 3 ? normalizePlanLevels(source.planLevels).slice(0, 6) : fallbackPlanLevels,
    reEvaluationTriggers: pickList(source.reEvaluationTriggers, observationSignals, 2, 5),
    suitableFor: pickText(source.suitableFor, "愿意按纪律分批执行、能接受阶段波动的交易者。"),
    unsuitableFor: pickText(source.unsuitableFor, "想一次性重仓或无法接受短线回撤的交易者。"),
    reasoning: pickList(source.reasoning, reasoningFallback, 3, 6),
    risks: pickList(source.risks, riskFlags, 2, 5),
    watchItems: pickList(source.watchItems, observationSignals, 2, 6),
    disclaimer: pickText(source.disclaimer, "本分析基于公开行情与新闻数据，仅供研究辅助，不构成投资建议。"),
  } satisfies StockAgentReport;

  return agentReportSchema.parse(report) as StockAgentReport;
}

function buildFallbackForecastScenarioInputs(report: StockAgentReport, toolOutputs: Map<string, Record<string, unknown> | null>) {
  const stockAnalysis = resolveToolContent(toolOutputs, "get_stock_analysis") as unknown as StockAnalysisResponse | null;
  const tradePlan = resolveToolContent(toolOutputs, "get_stock_trade_plan") as unknown as StockTradePlanSnapshot | null;
  const latest = stockAnalysis?.trendAnalysis.latest ?? null;
  const returns = stockAnalysis?.trendAnalysis.returns ?? null;
  const risk = stockAnalysis?.trendAnalysis.risk ?? null;
  const riskVolatility90d = normalizeNullableNumber(risk?.volatility90d) ?? 28;
  const maxDrawdown90d = Math.abs(normalizeNullableNumber(risk?.maxDrawdown90d) ?? -10);
  const upsideBase = clampNumber(Math.abs(normalizeNullableNumber(returns?.day20) ?? 0) * 0.6 + riskVolatility90d * 0.2, 6, 22);
  const downsideBase = clampNumber(maxDrawdown90d * 0.7 + 2, 5, 24);
  const confirmLevel = tradePlan?.planLevels.find((item) => item.kind === "观察确认位") ?? tradePlan?.planLevels[0] ?? null;
  const addLevel = tradePlan?.planLevels.find((item) => item.kind === "试探加仓位") ?? null;
  const riskLevel = tradePlan?.planLevels.find((item) => item.kind === "风控线") ?? tradePlan?.planLevels.at(-1) ?? null;
  const formatLevel = (nav: number | null | undefined) => (typeof nav === "number" ? nav.toFixed(2) : "关键位");

  if (report.outlook === "偏多") {
    return normalizeScenarioProbabilities([
      {
        label: "上行延续",
        probability: 38,
        targetReturn: roundTo(upsideBase, 2),
        summary: "若趋势和量价配合继续延续，股价大概率沿偏强结构抬升。",
        trigger: `若继续稳在 ${formatLevel(confirmLevel?.nav)} 上方，多头分支更容易兑现。`,
        volatility: riskVolatility90d >= 40 ? "高" : "中",
        pathStyle: latest?.signal === "多头排列" ? "震荡上行" : "先抑后扬",
      },
      {
        label: "高位震荡",
        probability: 36,
        targetReturn: roundTo(clampNumber(upsideBase * 0.35, 1, 8), 2),
        summary: "若增量催化不足，更可能围绕当前中枢反复拉锯。",
        trigger: `若围绕 ${formatLevel(addLevel?.nav ?? confirmLevel?.nav)} 一带来回震荡，说明市场仍在消化分歧。`,
        volatility: "中",
        pathStyle: "高位震荡",
      },
      {
        label: "回撤承压",
        probability: 26,
        targetReturn: roundTo(-downsideBase, 2),
        summary: "若风险重新主导，偏强结构会退化成回撤修正。",
        trigger: `若失守 ${formatLevel(riskLevel?.nav)}，下行分支概率会快速抬升。`,
        volatility: "高",
        pathStyle: "先扬后抑",
      },
    ]);
  }

  if (report.outlook === "偏谨慎") {
    return normalizeScenarioProbabilities([
      {
        label: "修复反弹",
        probability: 24,
        targetReturn: roundTo(clampNumber(upsideBase * 0.55, 3, 12), 2),
        summary: "若情绪修复并重新站上关键均线，仍有一段可交易反弹。",
        trigger: `若重新站上 ${formatLevel(confirmLevel?.nav)} 并连续站稳，修复分支会更可信。`,
        volatility: "中",
        pathStyle: "先抑后扬",
      },
      {
        label: "区间震荡",
        probability: 32,
        targetReturn: roundTo(clampNumber(-(downsideBase * 0.15), -4, 2), 2),
        summary: "若多空都拿不出决定性证据，股价更可能在区间内来回磨。",
        trigger: `若围绕 ${formatLevel(addLevel?.nav ?? confirmLevel?.nav)} 附近反复试探但没有单边突破，震荡情景会延续。`,
        volatility: "中",
        pathStyle: "区间震荡",
      },
      {
        label: "下行风险",
        probability: 44,
        targetReturn: roundTo(-clampNumber(downsideBase * 1.1, 6, 24), 2),
        summary: "如果核心风险继续发酵，股价仍可能延续弱势并向更低支撑寻找平衡。",
        trigger: `若跌破 ${formatLevel(riskLevel?.nav)}，偏谨慎分支会进一步强化。`,
        volatility: "高",
        pathStyle: "震荡下行",
      },
    ]);
  }

  return normalizeScenarioProbabilities([
    {
      label: "温和上行",
      probability: 30,
      targetReturn: roundTo(clampNumber(upsideBase * 0.7, 3, 15), 2),
      summary: "若利好边际改善，股价仍有机会走出温和修复上行。",
      trigger: `若逐步站稳 ${formatLevel(confirmLevel?.nav)} 上方，多头分支会更占优。`,
      volatility: "中",
      pathStyle: "震荡上行",
    },
    {
      label: "中性震荡",
      probability: 40,
      targetReturn: roundTo(clampNumber((normalizeNullableNumber(returns?.day5) ?? 0) * 0.2, -3, 3), 2),
      summary: "如果增量信息不足，股价大概率继续围绕当前中枢波动。",
      trigger: `若继续围绕 ${formatLevel(addLevel?.nav ?? confirmLevel?.nav)} 拉锯，说明市场仍未形成单边预期。`,
      volatility: "中",
      pathStyle: "区间震荡",
    },
    {
      label: "回落探底",
      probability: 30,
      targetReturn: roundTo(-clampNumber(downsideBase * 0.85, 5, 18), 2),
      summary: "若负面因素占优，股价更可能先回落探底，再等待新的平衡区间。",
      trigger: `若跌破 ${formatLevel(riskLevel?.nav)}，下行分支会更容易兑现。`,
      volatility: riskVolatility90d >= 36 ? "高" : "中",
      pathStyle: "先扬后抑",
    },
  ]);
}

function buildForecast(rawPayload: unknown, toolOutputs: Map<string, Record<string, unknown> | null>, report: StockAgentReport): StockAgentForecast | null {
  const stockAnalysis = resolveToolContent(toolOutputs, "get_stock_analysis") as unknown as StockAnalysisResponse | null;
  const latest = stockAnalysis?.trendAnalysis.latest ?? null;
  const riskVolatility90d = normalizeNullableNumber(stockAnalysis?.trendAnalysis.risk?.volatility90d) ?? null;

  if (!latest || typeof latest.close !== "number" || !latest.date) {
    return null;
  }

  const source = rawPayload && typeof rawPayload === "object" ? (rawPayload as Record<string, unknown>) : {};
  const normalizedInputs = normalizeForecastScenarioInputs(source.forecastScenarios);
  const scenarioInputs = normalizeScenarioProbabilities(
    normalizedInputs.length >= 2 ? normalizedInputs.slice(0, 4) : buildFallbackForecastScenarioInputs(report, toolOutputs),
  );
  const basePrice = roundTo(latest.close, 2);
  const baseDate = latest.date;

  const scenarios = scenarioInputs
    .map((scenario, index) => {
      const parsed = forecastScenarioSchema.parse(scenario);
      const targetPrice = roundTo(basePrice * (1 + parsed.targetReturn / 100), 2);
      return {
        id: `scenario-${index + 1}`,
        label: parsed.label,
        probability: parsed.probability,
        summary: parsed.summary,
        trigger: parsed.trigger,
        targetReturn: parsed.targetReturn,
        targetNav: targetPrice,
        volatility: parsed.volatility,
        pathStyle: parsed.pathStyle,
        points: createForecastPoints({
          baseDate,
          basePrice,
          targetReturn: parsed.targetReturn,
          volatility: parsed.volatility,
          pathStyle: parsed.pathStyle,
          riskVolatility90d,
        }),
      } satisfies StockAgentForecastScenario;
    })
    .sort((left, right) => right.probability - left.probability);

  return {
    horizon: report.horizon,
    baseDate,
    baseNav: basePrice,
    stepDays: FORECAST_STEP_DAYS,
    scenarios,
  } satisfies StockAgentForecast;
}

export class StockAgentService {
  private readonly registry = createFinancialMcpRegistry();

  private async executeTrackedTool<T extends Record<string, unknown>>(
    toolName: string,
    input: Record<string, unknown>,
    toolTrace: AgentToolTrace[],
    toolOutputs: Map<string, Record<string, unknown> | null>,
    options?: { swallowError?: boolean },
  ): Promise<T | null> {
    try {
      const toolResult = await this.registry.executeTool(toolName, input);
      const structuredContent = toolResult.structuredContent && typeof toolResult.structuredContent === "object"
        ? (toolResult.structuredContent as T)
        : null;
      toolOutputs.set(toolName, structuredContent);
      toolTrace.push({ toolName, summary: toolResult.summary });
      return structuredContent;
    } catch (error) {
      const summary = error instanceof Error ? `${toolName} 调用失败：${error.message}` : `${toolName} 调用失败。`;
      toolOutputs.set(toolName, null);
      toolTrace.push({ toolName, summary });
      if (options?.swallowError) {
        return null;
      }
      throw error;
    }
  }

  async analyzeStock(request: StockAgentRequest): Promise<StockAgentAnalysisResponse> {
    const stockCode = normalizeStockCode(request.stockCode);
    const horizon = String(request.horizon || DEFAULT_HORIZON).trim() || DEFAULT_HORIZON;
    const userQuestion = String(request.userQuestion || "").trim();
    const runtimeConfig = await resolveModelProviderRuntimeConfig();
    const client = new OpenAI({ apiKey: runtimeConfig.apiKey, baseURL: runtimeConfig.baseUrl });
    const promptAssets = await loadPromptAssets();
    const toolTrace: AgentToolTrace[] = [];
    const toolOutputs = new Map<string, Record<string, unknown> | null>();

    const stockAnalysis = await this.executeTrackedTool<StockAnalysisResponse>(
      "get_stock_analysis",
      { stockCode, historyDays: DEFAULT_ANALYSIS_HISTORY_DAYS },
      toolTrace,
      toolOutputs,
    );
    if (!stockAnalysis) {
      throw new Error("股票基础分析数据为空，无法继续生成结论。");
    }

    const tradePlan = await this.executeTrackedTool<StockTradePlanSnapshot>(
      "get_stock_trade_plan",
      { stockCode },
      toolTrace,
      toolOutputs,
    );
    if (!tradePlan) {
      throw new Error("股票交易计划数据为空，无法继续生成结论。");
    }

    const marketNews = await this.executeTrackedTool<FundMarketNewsQueryResponse>(
      "get_stock_market_news",
      buildStockNewsQueryArgs(stockAnalysis),
      toolTrace,
      toolOutputs,
      { swallowError: true },
    );

    const preparedContext = buildPreparedToolContext({
      horizon,
      stockAnalysis,
      tradePlan,
      marketNews,
    });

    const completion = await client.chat.completions.create({
      model: runtimeConfig.model,
      temperature: 0.15,
      messages: [
        {
          role: "system",
          content: buildSystemPrompt(promptAssets.skill),
        },
        {
          role: "system",
          content: [
            "以下是系统预抓的股票工具数据摘要，全部来自项目内数据工具，你必须把它们纳入最终结论。",
            JSON.stringify(preparedContext, null, 2),
          ].join("\n\n"),
        },
        {
          role: "user",
          content: buildUserPrompt({ stockCode, horizon, userQuestion }),
        },
      ] as never,
    });

    const rawText = extractTextContent(completion.choices[0]?.message?.content ?? "");
    const rawPayload = JSON.parse(extractJsonBlock(rawText));
    const report = finalizeReport(rawPayload, toolOutputs, horizon);
    const forecast = buildForecast(rawPayload, toolOutputs, report);

    return {
      runId: randomUUID(),
      stockCode,
      stockName: stockAnalysis.stock.name || null,
      generatedAt: new Date().toISOString(),
      model: runtimeConfig.model,
      toolTrace,
      report,
      forecast,
    };
  }
}
