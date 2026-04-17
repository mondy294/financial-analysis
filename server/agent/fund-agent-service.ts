import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import OpenAI from "openai";
import { z } from "zod";
import { getRequiredEnvValue, getEnvValue } from "../env.js";
import { createFinancialMcpRegistry } from "../mcp/registry.js";
import type {
  AgentToolTrace,
  FundAgentAnalysisResponse,
  FundAgentForecast,
  FundAgentForecastPathStyle,
  FundAgentForecastScenario,
  FundAgentForecastVolatility,
  FundAgentReport,
  FundAnalysisResponse,
  FundHoldingBreadthResponse,
  FundMarketNewsQueryResponse,
  FundPeerBenchmarkResponse,
  FundTradePlanLevel,
  FundTradePlanSnapshot,
} from "../types.js";

const DEFAULT_MODEL = getEnvValue(["DEEPSEEK_MODEL"], "deepseek-reasoner") || "deepseek-reasoner";

const DEFAULT_HORIZON = "未来 1-3 个月";
const MAX_TOOL_ROUNDS = 6;
const DEFAULT_ANALYSIS_HISTORY_DAYS = 365;
const DEFAULT_NEWS_LOOKBACK_DAYS = 21;
const DEFAULT_NEWS_LIMIT = 60;
const PREPARED_NEWS_ITEM_LIMIT = 12;

const planLevelKinds = ["观察确认位", "试探加仓位", "分批加仓位", "减仓位", "风控线"] as const;

const planLevelSchema = z.object({
  kind: z.enum(planLevelKinds),
  nav: z.number().nullable(),
  relativeToLatest: z.number().nullable(),
  reference: z.string().min(1),
  condition: z.string().min(6),
  action: z.string().min(4),
  reason: z.string().min(4),
});

const forecastVolatilityLevels = ["低", "中", "高"] as const;
const forecastPathStyles = ["震荡上行", "高位震荡", "区间震荡", "先抑后扬", "先扬后抑", "震荡下行"] as const;
const FORECAST_STEP_DAYS = 7;
const FORECAST_POINT_COUNT = 8;

const forecastScenarioSchema = z.object({
  label: z.string().min(2),
  probability: z.number().int().min(0).max(100),
  targetReturn: z.number().min(-40).max(40),
  summary: z.string().min(6),
  trigger: z.string().min(4),
  volatility: z.enum(forecastVolatilityLevels),
  pathStyle: z.enum(forecastPathStyles),
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

const listLeadLabelPattern = /^(?:可能原因(?:包括)?|核心依据(?:包括)?|主要风险(?:包括)?|风险提示(?:包括)?|需要关注(?:的)?(?:事项)?|接下来(?:盯|关注)(?:这些)?|观察点(?:包括)?|高重要度(?:事件|线索)(?:包括)?|外部催化(?:包括)?)[：:]\s*/;
const listPrefixPattern = /^[\s"'“”‘’【\[（(]*?(?:[-•*·▪◦]+\s*|\d+[）)、:：]\s*|\d+\.\s+|[一二三四五六七八九十]+[）)、:：]\s*|[一二三四五六七八九十]+、\s*)/;
const inlineEnumerationPattern = /(?:^|[：:]\s*|\s+)(?:[-•*·▪◦]+\s*|\d+[）)、]\s*|\d+\.\s+|[一二三四五六七八九十]+[）)、]\s*|[一二三四五六七八九十]+、\s*)/g;

function normalizeInlineText(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

function stripListLeadText(value: string) {
  let text = normalizeInlineText(value).replace(listLeadLabelPattern, "").trim();

  while (text) {
    const next = text
      .replace(listPrefixPattern, "")
      .replace(/^[）)】]+\s*/, "")
      .replace(/^[：:，,；;]+\s*/, "")
      .trim();

    if (next === text) {
      break;
    }
    text = next;
  }

  return text.trim();
}

function explodeInlineNumberedPoints(value: string) {
  const normalized = stripListLeadText(value);
  const withBreaks = normalized.replace(inlineEnumerationPattern, "\n");

  return withBreaks
    .split(/\n+/)
    .map((segment) => stripListLeadText(segment))
    .filter(Boolean);
}

function dedupeTextItems(items: string[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item)) {
      return false;
    }
    seen.add(item);
    return true;
  });
}

function normalizeStringList(value: unknown) {
  if (Array.isArray(value)) {
    return dedupeTextItems(
      value
        .flatMap((item) => (typeof item === "string" ? explodeInlineNumberedPoints(item) : []))
        .filter((item) => item.length >= 4),
    );
  }

  if (typeof value === "string") {
    return dedupeTextItems(
      value
        .split(/\r?\n|；|;/)
        .flatMap((item) => explodeInlineNumberedPoints(item))
        .filter((item) => item.length >= 4),
    );
  }

  return [];
}

function normalizeNullableNumber(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function clampNumber(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function roundTo(value: number, digits: number) {
  return Number(value.toFixed(digits));
}

function calculateBollingerPositionPercent(nav: number | null | undefined, lower: number | null | undefined, upper: number | null | undefined) {
  if (typeof nav !== "number" || !Number.isFinite(nav)) {
    return null;
  }
  if (typeof lower !== "number" || !Number.isFinite(lower)) {
    return null;
  }
  if (typeof upper !== "number" || !Number.isFinite(upper) || upper === lower) {
    return null;
  }

  return roundTo(((nav - lower) / (upper - lower)) * 100, 2);
}

function shiftDateByDays(dateText: string, days: number) {
  const date = new Date(`${dateText}T00:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function easeInOutSine(progress: number) {
  return -(Math.cos(Math.PI * progress) - 1) / 2;
}

function normalizePlanLevels(value: unknown): FundTradePlanLevel[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => {
      const source = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
      const kind = typeof source.kind === "string" ? source.kind.trim() : "";
      return {
        kind,
        nav: normalizeNullableNumber(source.nav),
        relativeToLatest: normalizeNullableNumber(source.relativeToLatest),
        reference: typeof source.reference === "string" ? source.reference.trim() : "",
        condition: typeof source.condition === "string" ? source.condition.trim() : "",
        action: typeof source.action === "string" ? source.action.trim() : "",
        reason: typeof source.reason === "string" ? source.reason.trim() : "",
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

function normalizeReportPayload(value: unknown) {
  const source = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  return {
    ...source,
    recentWeekDrivers: normalizeStringList(source.recentWeekDrivers),
    executionRules: normalizeStringList(source.executionRules),
    reEvaluationTriggers: normalizeStringList(source.reEvaluationTriggers),
    reasoning: normalizeStringList(source.reasoning),
    risks: normalizeStringList(source.risks),
    watchItems: normalizeStringList(source.watchItems),
    planLevels: normalizePlanLevels(source.planLevels),
  };
}

function pickText(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim().length > 0 ? stripListLeadText(value) : fallback;
}

function pickList(value: unknown, fallback: string[], minimum: number, maximum: number) {
  const primary = normalizeStringList(value);
  const merged = primary.length >= minimum ? primary : fallback;
  return merged.slice(0, maximum).filter(Boolean);
}

type ForecastScenarioInput = {
  label: string;
  probability: number;
  targetReturn: number;
  summary: string;
  trigger: string;
  volatility: FundAgentForecastVolatility;
  pathStyle: FundAgentForecastPathStyle;
};

function normalizeForecastVolatility(value: unknown): FundAgentForecastVolatility {
  return forecastVolatilityLevels.includes(value as FundAgentForecastVolatility) ? (value as FundAgentForecastVolatility) : "中";
}

function normalizeForecastPathStyle(value: unknown): FundAgentForecastPathStyle {
  return forecastPathStyles.includes(value as FundAgentForecastPathStyle) ? (value as FundAgentForecastPathStyle) : "区间震荡";
}

function normalizeForecastScenarioInputs(value: unknown) {
  if (!Array.isArray(value)) {
    return [] as ForecastScenarioInput[];
  }

  return value
    .map((item) => {
      const source = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
      const probability = normalizeNullableNumber(source.probability);
      const targetReturn = normalizeNullableNumber(source.targetReturn);
      return {
        label: pickText(source.label, "情景预测"),
        probability: probability === null ? 0 : clampNumber(Math.round(probability), 0, 100),
        targetReturn: targetReturn === null ? 0 : clampNumber(roundTo(targetReturn, 2), -40, 40),
        summary: pickText(source.summary, "未来路径仍需继续观察。"),
        trigger: pickText(source.trigger, "继续观察关键价位与外部催化。"),
        volatility: normalizeForecastVolatility(source.volatility),
        pathStyle: normalizeForecastPathStyle(source.pathStyle),
      } satisfies ForecastScenarioInput;
    })
    .filter((item) => item.label.length >= 2 && item.summary.length >= 6);
}

function normalizeScenarioProbabilities(scenarios: ForecastScenarioInput[]) {
  if (scenarios.length === 0) {
    return scenarios;
  }

  const rawTotal = scenarios.reduce((total, item) => total + item.probability, 0);
  if (rawTotal === 100) {
    return scenarios;
  }

  if (rawTotal <= 0) {
    const evenProbability = Math.floor(100 / scenarios.length);
    let remainder = 100 - evenProbability * scenarios.length;
    return scenarios.map((item) => {
      const delta = remainder > 0 ? 1 : 0;
      remainder -= delta;
      return {
        ...item,
        probability: evenProbability + delta,
      } satisfies ForecastScenarioInput;
    });
  }

  const normalized = scenarios.map((item) => ({
    ...item,
    probability: Math.max(1, Math.round((item.probability / rawTotal) * 100)),
  }));
  let drift = 100 - normalized.reduce((total, item) => total + item.probability, 0);

  const sortedIndexes = normalized
    .map((item, index) => ({ index, probability: item.probability }))
    .sort((left, right) => right.probability - left.probability)
    .map((item) => item.index);

  for (const index of sortedIndexes) {
    if (drift === 0) {
      break;
    }
    if (drift > 0) {
      normalized[index] = {
        ...normalized[index],
        probability: normalized[index].probability + 1,
      };
      drift -= 1;
      continue;
    }
    if (normalized[index].probability > 1) {
      normalized[index] = {
        ...normalized[index],
        probability: normalized[index].probability - 1,
      };
      drift += 1;
    }
  }

  return normalized;
}

function calculateForecastWave(progress: number, amplitude: number, pathStyle: FundAgentForecastPathStyle) {
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

function createForecastPoints(input: {
  baseDate: string;
  baseNav: number;
  targetReturn: number;
  volatility: FundAgentForecastVolatility;
  pathStyle: FundAgentForecastPathStyle;
  riskVolatility90d: number | null;
}) {
  const baseAmplitude = clampNumber((input.riskVolatility90d ?? 18) / Math.sqrt(52), 1.2, 8);
  const amplitudeMultiplier = input.volatility === "高" ? 1.05 : input.volatility === "低" ? 0.55 : 0.8;
  const amplitude = baseAmplitude * amplitudeMultiplier;

  return Array.from({ length: FORECAST_POINT_COUNT }, (_, index) => {
    const step = index + 1;
    const progress = step / FORECAST_POINT_COUNT;
    const easedReturn = input.targetReturn * easeInOutSine(progress);
    const wave = step === FORECAST_POINT_COUNT ? 0 : calculateForecastWave(progress, amplitude, input.pathStyle);
    const returnRate = roundTo(easedReturn + wave, 2);
    const nav = roundTo(Math.max(0.01, input.baseNav * (1 + returnRate / 100)), 4);

    return {
      date: shiftDateByDays(input.baseDate, step * FORECAST_STEP_DAYS),
      nav,
      returnRate,
    };
  });
}

function resolveToolContent(toolOutputs: Map<string, Record<string, unknown> | null>, toolName: string) {
  return toolOutputs.get(toolName) ?? null;
}

function fallbackOutlook(signal: unknown): FundAgentReport["outlook"] {
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

function fallbackActionTag(outlook: FundAgentReport["outlook"], hasHolding: boolean): FundAgentReport["actionTag"] {
  if (outlook === "偏多") {
    return hasHolding ? "持有待跟踪" : "分批布局";
  }
  if (outlook === "偏谨慎") {
    return hasHolding ? "谨慎减仓" : "观望为主";
  }
  return hasHolding ? "持有待跟踪" : "观望为主";
}

function fallbackReasoning(toolOutputs: Map<string, Record<string, unknown> | null>) {
  const reasons: string[] = [];
  const fundAnalysis = resolveToolContent(toolOutputs, "get_fund_analysis");
  const latest = (fundAnalysis?.trendAnalysis as { latest?: Record<string, unknown> } | undefined)?.latest ?? null;
  const returns = (fundAnalysis?.trendAnalysis as { returns?: Record<string, unknown> } | undefined)?.returns ?? null;
  const peer = resolveToolContent(toolOutputs, "get_fund_peer_benchmark");
  const percentile = (peer?.percentile as Record<string, unknown> | undefined) ?? null;
  const breadth = resolveToolContent(toolOutputs, "get_fund_holding_breadth");
  const tradePlan = resolveToolContent(toolOutputs, "get_fund_trade_plan");
  const holding = (tradePlan?.holding as Record<string, unknown> | undefined) ?? null;
  const marketNews = resolveToolContent(toolOutputs, "get_fund_market_news") as unknown as FundMarketNewsQueryResponse | null;

  const signal = latest?.signal;
  if (typeof signal === "string") {
    reasons.push(`趋势结构：当前更接近 ${signal}。`);
  }

  const biasToMa20 = normalizeNullableNumber(latest?.biasToMa20);
  if (typeof biasToMa20 === "number") {
    const biasDescription = Math.abs(biasToMa20) >= 8
      ? "和中期均线拉开得比较明显"
      : Math.abs(biasToMa20) >= 3
        ? "已经出现一定偏离"
        : "说明当前离中期均线并不远";
    reasons.push(`净值相对 MA20 乖离约 ${biasToMa20.toFixed(2)}%，${biasDescription}。`);
  }

  const bollWidth20 = normalizeNullableNumber(latest?.bollWidth20);
  const bollPositionPercent = calculateBollingerPositionPercent(
    normalizeNullableNumber(latest?.nav),
    normalizeNullableNumber(latest?.bollLower),
    normalizeNullableNumber(latest?.bollUpper),
  );
  if (typeof bollWidth20 === "number") {
    const widthDescription = bollWidth20 >= 12 ? "带宽偏宽，短线波动在放大" : bollWidth20 <= 4 ? "带宽偏窄，走势更接近收敛等待方向" : "波动处在中性区间";
    reasons.push(`20 日布林带宽约 ${bollWidth20.toFixed(2)}%，${widthDescription}。`);
  }
  if (typeof bollPositionPercent === "number") {
    const positionDescription = bollPositionPercent >= 85
      ? "净值已经贴近布林上轨，追高要更谨慎"
      : bollPositionPercent <= 15
        ? "净值逼近布林下轨，不能把弱势直接当成企稳"
        : "净值仍在布林中部区域运行";
    reasons.push(`当前布林带位置约在 ${bollPositionPercent.toFixed(2)}% 分位，${positionDescription}。`);
  }

  const return60 = normalizeNullableNumber(returns?.day60);
  if (typeof return60 === "number") {
    reasons.push(`近 60 个交易日收益约 ${return60.toFixed(2)}%，可用来区分是中期修复还是继续走弱。`);
  }

  const peerReturn3m = normalizeNullableNumber(percentile?.return3m);
  if (typeof peerReturn3m === "number") {
    reasons.push(`同类近 3 个月收益分位约 ${peerReturn3m.toFixed(1)}，能辅助判断相对强弱。`);
  }

  const concentrationTop5 = normalizeNullableNumber(breadth?.concentrationTop5);
  if (typeof concentrationTop5 === "number") {
    reasons.push(`前 5 大重仓股集中度约 ${concentrationTop5.toFixed(2)}%，集中度越高越要防范个股拖累。`);
  }

  const positionRatio = normalizeNullableNumber(holding?.portfolioPositionRatio);
  if (typeof positionRatio === "number") {
    reasons.push(`当前这只基金约占组合 ${positionRatio.toFixed(2)}%，仓位动作需要和整体组合权重一起看。`);
  }

  reasons.push(...buildNewsEvidenceHighlights(marketNews));

  return dedupeTextItems(reasons).slice(0, 6);
}

function fallbackExecutionRules(toolOutputs: Map<string, Record<string, unknown> | null>) {
  const tradePlan = resolveToolContent(toolOutputs, "get_fund_trade_plan");
  const planLevels = normalizePlanLevels(tradePlan?.planLevels);
  return planLevels.map((level) => `${level.condition}；执行：${level.action}`).slice(0, 6);
}

function buildFallbackHoldingContext(toolOutputs: Map<string, Record<string, unknown> | null>) {
  const tradePlan = resolveToolContent(toolOutputs, "get_fund_trade_plan");
  const holding = (tradePlan?.holding as Record<string, unknown> | undefined) ?? null;
  const hasHolding = Boolean(holding?.hasHolding);
  if (!hasHolding) {
    return "当前没有本地持仓记录，建议先按观察仓或试探仓思路处理。";
  }

  const positionAmount = normalizeNullableNumber(holding?.positionAmount);
  const costNav = normalizeNullableNumber(holding?.costNav);
  const currentProfitRate = normalizeNullableNumber(holding?.currentProfitRate);
  const portfolioPositionRatio = normalizeNullableNumber(holding?.portfolioPositionRatio);

  return [
    `当前已有持仓${positionAmount !== null ? `，持仓金额约 ${positionAmount.toFixed(2)} 元` : ""}`,
    costNav !== null ? `成本净值约 ${costNav.toFixed(4)}` : "",
    currentProfitRate !== null ? `当前收益率约 ${currentProfitRate.toFixed(2)}%` : "",
    portfolioPositionRatio !== null ? `占组合约 ${portfolioPositionRatio.toFixed(2)}%` : "",
  ]
    .filter(Boolean)
    .join("，");
}

function finalizeReport(rawReport: unknown, toolOutputs: Map<string, Record<string, unknown> | null>, horizon: string) {
  const normalized = normalizeReportPayload(rawReport) as Record<string, unknown>;
  const tradePlan = resolveToolContent(toolOutputs, "get_fund_trade_plan");
  const fundAnalysis = resolveToolContent(toolOutputs, "get_fund_analysis");
  const latest = (fundAnalysis?.trendAnalysis as { latest?: Record<string, unknown> } | undefined)?.latest ?? null;
  const sizingSuggestion = (tradePlan?.sizingSuggestion as Record<string, unknown> | undefined) ?? null;
  const riskFlags = normalizeStringList(tradePlan?.riskFlags);
  const observationSignals = normalizeStringList(tradePlan?.observationSignals);
  const hasHolding = Boolean((tradePlan?.holding as Record<string, unknown> | undefined)?.hasHolding);
  const fallbackPlanLevels = normalizePlanLevels(tradePlan?.planLevels).slice(0, 6);
  const fallbackRules = fallbackExecutionRules(toolOutputs);
  const reasoningFallback = fallbackReasoning(toolOutputs);
  const outlook = (["偏多", "中性", "偏谨慎", "无法判断"] as const).includes(normalized.outlook as FundAgentReport["outlook"])
    ? (normalized.outlook as FundAgentReport["outlook"])
    : fallbackOutlook(latest?.signal);
  const actionTag = (["观望为主", "分批布局", "持有待跟踪", "谨慎减仓"] as const).includes(normalized.actionTag as FundAgentReport["actionTag"])
    ? (normalized.actionTag as FundAgentReport["actionTag"])
    : fallbackActionTag(outlook, hasHolding);
  const confidence = (() => {
    const numeric = normalizeNullableNumber(normalized.confidence);
    if (numeric === null) {
      return 62;
    }
    return Math.max(0, Math.min(100, Math.round(numeric)));
  })();

  const report = {
    horizon: pickText(normalized.horizon, horizon),
    outlook,
    confidence,
    recentWeekSummary: pickText(normalized.recentWeekSummary, pickText(normalized.summary, "最近一周仍在延续原有趋势，短期变化需要结合支撑位和同类位置继续观察。")),
    recentWeekDrivers: pickList(normalized.recentWeekDrivers, reasoningFallback, 2, 6),
    summary: pickText(normalized.summary, "当前结论需要结合趋势、同类位置和持仓结构一起看。"),
    actionTag,
    actionAdvice: pickText(normalized.actionAdvice, typeof sizingSuggestion?.currentActionBias === "string" ? sizingSuggestion.currentActionBias : "当前先按保守节奏处理，不要一次性放大动作。"),
    holdingContext: pickText(normalized.holdingContext, buildFallbackHoldingContext(toolOutputs)),
    positionInstruction: pickText(normalized.positionInstruction, pickText(normalized.actionAdvice, "先按计划位观察，不要脱离阈值随意加减仓。")),
    positionSizing: pickText(
      normalized.positionSizing,
      typeof sizingSuggestion?.addOnDip === "string" ? sizingSuggestion.addOnDip : hasHolding ? "单次动作以当前持仓金额的小比例分批为主。" : "先用小比例试探仓参与。",
    ),
    planSummary: pickText(normalized.planSummary, typeof sizingSuggestion?.currentActionBias === "string" ? sizingSuggestion.currentActionBias : "当前以观察关键价位和分批动作为主。"),
    executionRules: pickList(normalized.executionRules, fallbackRules, 3, 6),
    planLevels: (normalized.planLevels as FundAgentReport["planLevels"]).length >= 3 ? (normalized.planLevels as FundAgentReport["planLevels"]).slice(0, 6) : fallbackPlanLevels,
    reEvaluationTriggers: pickList(normalized.reEvaluationTriggers, observationSignals, 2, 5),
    suitableFor: pickText(normalized.suitableFor, "愿意按计划分批执行、能接受阶段波动的投资者。"),
    unsuitableFor: pickText(normalized.unsuitableFor, "希望一次性重仓、不能接受回撤或只看短期波动的投资者。"),
    reasoning: pickList(normalized.reasoning, reasoningFallback, 3, 6),
    risks: pickList(normalized.risks, riskFlags, 2, 5),
    watchItems: pickList(normalized.watchItems, observationSignals, 2, 6),
    disclaimer: pickText(normalized.disclaimer, "本分析基于公开数据与本地持仓记录，仅供研究辅助，不构成投资建议。"),
  } satisfies FundAgentReport;

  return agentReportSchema.parse(report) as FundAgentReport;
}

function buildFallbackForecastScenarioInputs(
  report: FundAgentReport,
  toolOutputs: Map<string, Record<string, unknown> | null>,
) {
  const fundAnalysis = resolveToolContent(toolOutputs, "get_fund_analysis") as unknown as FundAnalysisResponse | null;
  const latest = fundAnalysis?.trendAnalysis.latest ?? null;
  const returns = fundAnalysis?.trendAnalysis.returns ?? null;
  const risk = fundAnalysis?.trendAnalysis.risk ?? null;
  const riskVolatility90d = normalizeNullableNumber(risk?.volatility90d) ?? 18;
  const maxDrawdown90d = Math.abs(normalizeNullableNumber(risk?.maxDrawdown90d) ?? -8);
  const upsideBase = clampNumber(Math.abs(normalizeNullableNumber(returns?.day20) ?? 0) * 0.55 + riskVolatility90d * 0.18, 4, 16);
  const downsideBase = clampNumber(maxDrawdown90d * 0.6 + 2.5, 4, 18);
  const confidenceSkew = clampNumber(Math.round((report.confidence - 60) / 3), -8, 12);
  const confirmLevel = report.planLevels.find((item) => item.kind === "观察确认位") ?? report.planLevels[0] ?? null;
  const addLevel = report.planLevels.find((item) => item.kind === "试探加仓位") ?? report.planLevels[1] ?? null;
  const reduceLevel = report.planLevels.find((item) => item.kind === "减仓位") ?? null;
  const riskLevel = report.planLevels.find((item) => item.kind === "风控线") ?? report.planLevels.at(-1) ?? null;
  const formatLevel = (nav: number | null | undefined) => (typeof nav === "number" ? nav.toFixed(4) : "关键位");

  if (report.outlook === "偏多") {
    const bullish = clampNumber(34 + confidenceSkew, 24, 52);
    const neutral = clampNumber(42 - Math.round(confidenceSkew / 2), 28, 50);
    const cautious = 100 - bullish - neutral;
    return normalizeScenarioProbabilities([
      {
        label: "上行延续",
        probability: bullish,
        targetReturn: roundTo(upsideBase, 2),
        summary: "若趋势与外部催化继续配合，净值大概率沿着当前偏强结构继续抬升。",
        trigger: `若净值持续稳在 ${formatLevel(confirmLevel?.nav)} 上方，偏多分支更容易兑现。`,
        volatility: riskVolatility90d >= 28 ? "高" : "中",
        pathStyle: latest?.signal === "多头排列" ? "震荡上行" : "先抑后扬",
      },
      {
        label: "高位震荡",
        probability: neutral,
        targetReturn: roundTo(clampNumber(Math.max(upsideBase * 0.35, 1.2), -2, 6), 2),
        summary: "如果增量催化不足，基金更可能围绕当前中枢反复拉锯，以消化前期波动。",
        trigger: `若净值围绕 ${formatLevel(addLevel?.nav ?? confirmLevel?.nav)} 一带反复震荡，说明市场还在消化分歧。`,
        volatility: "中",
        pathStyle: "高位震荡",
      },
      {
        label: "回撤承压",
        probability: cautious,
        targetReturn: roundTo(-downsideBase, 2),
        summary: "一旦风险重新主导，当前偏多结构可能退化成回撤修正，净值会向更低支撑回落。",
        trigger: `若净值失守 ${formatLevel(riskLevel?.nav)} 或主要风险兑现，下行分支概率会快速抬升。`,
        volatility: "高",
        pathStyle: "先扬后抑",
      },
    ]);
  }

  if (report.outlook === "偏谨慎") {
    const bearish = clampNumber(34 + confidenceSkew, 24, 56);
    const neutral = clampNumber(38 - Math.round(confidenceSkew / 3), 24, 44);
    const rebound = 100 - bearish - neutral;
    return normalizeScenarioProbabilities([
      {
        label: "修复反弹",
        probability: rebound,
        targetReturn: roundTo(clampNumber(upsideBase * 0.55, 2, 10), 2),
        summary: "若外部扰动缓和并出现估值修复，基金仍有一段可交易的反弹窗口。",
        trigger: `若净值重新站上 ${formatLevel(confirmLevel?.nav)} 并连续站稳，修复分支会更可信。`,
        volatility: "中",
        pathStyle: "先抑后扬",
      },
      {
        label: "区间震荡",
        probability: neutral,
        targetReturn: roundTo(clampNumber(-(downsideBase * 0.15), -3, 1.5), 2),
        summary: "若多空都拿不出决定性证据，净值更可能继续在区间内来回磨。",
        trigger: `若净值在 ${formatLevel(addLevel?.nav ?? confirmLevel?.nav)} 附近反复试探但始终没有单边突破，震荡情景会延续。`,
        volatility: "中",
        pathStyle: "区间震荡",
      },
      {
        label: "下行风险",
        probability: bearish,
        targetReturn: roundTo(-clampNumber(downsideBase * 1.1, 4, 18), 2),
        summary: "如果核心风险继续发酵，净值仍可能延续弱势并向更低支撑寻找平衡。",
        trigger: `若净值跌破 ${formatLevel(riskLevel?.nav)}，偏谨慎分支会进一步强化。`,
        volatility: "高",
        pathStyle: "震荡下行",
      },
    ]);
  }

  const bullish = clampNumber(28 + Math.max(0, confidenceSkew), 18, 42);
  const neutral = clampNumber(44 - Math.round(confidenceSkew / 4), 30, 52);
  const cautious = 100 - bullish - neutral;
  return normalizeScenarioProbabilities([
    {
      label: "温和上行",
      probability: bullish,
      targetReturn: roundTo(clampNumber(upsideBase * 0.7, 2, 12), 2),
      summary: "若利好边际改善，基金仍有机会走出偏温和的修复上行。",
      trigger: `若净值逐步站稳 ${formatLevel(confirmLevel?.nav)} 上方，多头分支会更占优。`,
      volatility: "中",
      pathStyle: "震荡上行",
    },
    {
      label: "中性震荡",
      probability: neutral,
      targetReturn: roundTo(clampNumber((normalizeNullableNumber(returns?.day5) ?? 0) * 0.2, -2, 2), 2),
      summary: "如果资金与消息面都没有明显倾斜，净值大概率继续围绕当前中枢波动。",
      trigger: `若净值继续围绕 ${formatLevel(addLevel?.nav ?? confirmLevel?.nav)} 拉锯，说明市场仍未形成单边预期。`,
      volatility: "中",
      pathStyle: "区间震荡",
    },
    {
      label: "回落探底",
      probability: cautious,
      targetReturn: roundTo(-clampNumber(downsideBase * 0.85, 3, 14), 2),
      summary: "若负面因素占优，净值更可能先回落探底，再等待新的平衡区间。",
      trigger: `若净值跌破 ${formatLevel(riskLevel?.nav ?? reduceLevel?.nav)}，下行分支会更容易兑现。`,
      volatility: riskVolatility90d >= 26 ? "高" : "中",
      pathStyle: "先扬后抑",
    },
  ]);
}

function buildForecast(
  rawPayload: unknown,
  toolOutputs: Map<string, Record<string, unknown> | null>,
  report: FundAgentReport,
): FundAgentForecast | null {
  const fundAnalysis = resolveToolContent(toolOutputs, "get_fund_analysis") as unknown as FundAnalysisResponse | null;
  const latest = fundAnalysis?.trendAnalysis.latest ?? null;
  const riskVolatility90d = normalizeNullableNumber(fundAnalysis?.trendAnalysis.risk?.volatility90d) ?? null;

  if (!latest || typeof latest.nav !== "number" || !latest.date) {
    return null;
  }

  const source = rawPayload && typeof rawPayload === "object" ? (rawPayload as Record<string, unknown>) : {};
  const normalizedScenarioInputs = normalizeForecastScenarioInputs(source.forecastScenarios);
  const scenarioInputs = normalizeScenarioProbabilities(
    normalizedScenarioInputs.length >= 2 ? normalizedScenarioInputs.slice(0, 4) : buildFallbackForecastScenarioInputs(report, toolOutputs),
  );
  const baseNav = roundTo(latest.nav, 4);
  const baseDate = latest.date;

  const scenarios = scenarioInputs
    .map((scenario, index) => {
      const parsedScenario = forecastScenarioSchema.parse(scenario);
      const targetNav = roundTo(baseNav * (1 + parsedScenario.targetReturn / 100), 4);
      const points = createForecastPoints({
        baseDate,
        baseNav,
        targetReturn: parsedScenario.targetReturn,
        volatility: parsedScenario.volatility,
        pathStyle: parsedScenario.pathStyle,
        riskVolatility90d,
      });

      return {
        id: `scenario-${index + 1}`,
        label: parsedScenario.label,
        probability: parsedScenario.probability,
        summary: parsedScenario.summary,
        trigger: parsedScenario.trigger,
        targetReturn: parsedScenario.targetReturn,
        targetNav,
        volatility: parsedScenario.volatility,
        pathStyle: parsedScenario.pathStyle,
        points,
      } satisfies FundAgentForecastScenario;
    })
    .sort((left, right) => right.probability - left.probability);

  return {
    horizon: report.horizon,
    baseDate,
    baseNav,
    stepDays: FORECAST_STEP_DAYS,
    scenarios,
  } satisfies FundAgentForecast;
}

type FundAgentRequest = {
  fundCode: string;
  userQuestion?: string | null;
  horizon?: string | null;
};

type PromptAssets = {
  skill: string;
  reference: string;
};

let promptAssetsCache: PromptAssets | null = null;

function normalizeFundCode(code: string) {
  const cleanCode = String(code || "").trim();
  if (!/^\d{6}$/.test(cleanCode)) {
    throw new Error("基金编号必须是 6 位数字。");
  }
  return cleanCode;
}

async function loadPromptAssets(): Promise<PromptAssets> {
  if (promptAssetsCache) {
    return promptAssetsCache;
  }

  const skillPath = path.resolve(process.cwd(), "server/agent/skills/fund-trend-analyst/SKILL.md");
  const referencePath = path.resolve(process.cwd(), "server/agent/references/fund-analysis-playbook.md");
  const [skill, reference] = await Promise.all([
    fs.readFile(skillPath, "utf-8"),
    fs.readFile(referencePath, "utf-8"),
  ]);

  promptAssetsCache = { skill, reference };
  return promptAssetsCache;
}

function buildSystemPrompt(skill: string, reference: string) {
  return [
    "你是项目内的基金走势分析 Agent。",
    "你必须优先调用项目提供的工具获取数据，再给出未来 1-3 个月走势判断和当前操作建议。",
    "你只能基于工具返回的数据发言，不得编造不存在的经理信息、宏观信息、持仓信息或收益承诺。",
    "系统可能已预取核心工具结果与市场新闻摘要；这些都是真实工具输出，属于强制证据，不能忽略。",
    "无论用户是否主动提到新闻，你都要把近期市场新闻与基金当前、历史数据交叉验证，用来解释最近一周扰动和未来 1-3 个月潜在催化/风险。",
    "请明确区分：趋势判断、操作建议、风险提示、待观察指标、交易计划阈值。",
    "如果证据互相冲突，允许给出中性或无法判断，而不是硬凑单边结论。",
    "如果用户没有本地持仓，不要写成仓位管理结论，要偏向观察/分批。",
    "只要用户需要‘跌到多少加仓 / 反弹到多少减仓 / 现在该怎么做’这类计划，你必须调用 get_fund_trade_plan，并把其中的关键阈值转成结构化结论。",
    "最终只输出合法 JSON，不要输出 Markdown，不要输出代码块。",
    "JSON 顶层必须严格包含这些字段：horizon,outlook,confidence,recentWeekSummary,recentWeekDrivers,summary,actionTag,actionAdvice,holdingContext,positionInstruction,positionSizing,planSummary,executionRules,planLevels,reEvaluationTriggers,suitableFor,unsuitableFor,reasoning,risks,watchItems,disclaimer,forecastScenarios。",
    "所有数组字段中的每一项都必须是干净完整的一句话，不要保留 1）/2）/• 之类编号前缀，也不要把多个要点塞进同一个数组元素。",
    "confidence 取 0-100 的整数。",
    "outlook 只能是：偏多 / 中性 / 偏谨慎 / 无法判断。",
    "actionTag 只能是：观望为主 / 分批布局 / 持有待跟踪 / 谨慎减仓。",
    "planLevels 必须给出 3-6 个关键价位，至少包含一个加仓相关价位和一个风控线；nav 与 relativeToLatest 使用数字或 null。",
    "executionRules 必须写成可以执行的句子，例如‘若净值跌到 X 以下但未破位，则...’。",
    "forecastScenarios 必须返回 2-4 条，每条必须包含 label,probability,targetReturn,summary,trigger,volatility,pathStyle。",
    "forecastScenarios 里 probability 必须是 0-100 的整数，全部场景加总必须等于 100。",
    "targetReturn 表示相对当前净值的未来目标涨跌幅（百分比，可正可负）。",
    "volatility 只能是：低 / 中 / 高。",
    "pathStyle 只能是：震荡上行 / 高位震荡 / 区间震荡 / 先抑后扬 / 先扬后抑 / 震荡下行。",
    "disclaimer 必须明确表达“仅供研究辅助，不构成投资建议”。",
    "以下是你的 Skill：",
    skill,
    "以下是你的 Reference：",
    reference,
  ].join("\n\n");
}

function buildUserPrompt(input: { fundCode: string; horizon: string; userQuestion: string }) {
  const extraUserContext = input.userQuestion.trim();

  return [
    `请分析基金 ${input.fundCode}。`,
    `目标周期：${input.horizon}。`,
    extraUserContext ? `用户补充信息：${extraUserContext}` : null,
    "系统已预先准备至少 1 年的历史走势、同类对标、交易计划，以及近 21 天的国内外市场新闻摘要。你必须把这些证据一起用于近期与未来 1-3 个月判断。",
    "如果预抓摘要仍不够，可以继续调用工具补充，但不能忽略市场新闻与当前/历史数据的联合验证。",
    "请先说明最近一周发生了什么，再说明最近 7-30 天外部事件与基金当前/历史数据如何互相印证，最后给出未来 1-3 个月判断。数组字段请直接输出要点本身，不要写编号前缀。",
    "如果存在本地持仓，请结合当前持仓金额、成本净值和组合占比，给出更具体的仓位动作与幅度范围。",
    "请明确回答：现在应该做什么、跌到什么净值附近可以考虑加仓、反弹到什么净值附近更适合减仓、什么条件出现就需要重新评估。",
    "除了分析结论，还要输出 2-4 条未来路径预测分支，说明每条分支的概率、目标涨跌幅、简短解释和触发条件。",
    "输出时不要出现任何多余字段。",
  ].filter(Boolean).join("\n");
}

function truncateText(value: string, maxLength = 120) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
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

function buildFundNewsQueryArgs(fundAnalysis: FundAnalysisResponse) {
  const now = new Date();
  const startDate = new Date(now.getTime() - DEFAULT_NEWS_LOOKBACK_DAYS * 24 * 60 * 60 * 1000);
  const category = fundAnalysis.screener?.category ?? null;
  const topics = category === "纯债" || category === "固收+"
    ? ["基金", "债券", "央行", "经济数据", "外汇", "地区"]
    : ["焦点", "基金", "全球股市", "商品", "外汇", "债券", "地区", "央行", "经济数据"];

  return {
    startTime: formatShanghaiDateTime(startDate),
    endTime: formatShanghaiDateTime(now),
    regions: ["国内", "海外"] as const,
    topics,
    limit: DEFAULT_NEWS_LIMIT,
  };
}

function formatCountBreakdown(items: Array<{ label: string; count: number }>, fallback: string) {
  if (!items.length) {
    return fallback;
  }

  return items
    .slice()
    .sort((left, right) => right.count - left.count)
    .slice(0, 3)
    .map((item) => `${item.label}(${item.count})`)
    .join("、");
}

function buildMarketNewsDigest(marketNews: FundMarketNewsQueryResponse | null, fallbackSummary?: string | null) {
  if (!marketNews || marketNews.items.length === 0) {
    return fallbackSummary || "近期市场新闻暂未取到，请谨慎处理外部催化判断。";
  }

  const topicSummary = formatCountBreakdown(
    marketNews.stats.byTopic.map((item) => ({ label: item.topic, count: item.count })),
    "暂无明显主题集中",
  );
  const regionSummary = formatCountBreakdown(
    marketNews.stats.byRegion.map((item) => ({ label: item.region, count: item.count })),
    "暂无明显地区集中",
  );
  const highlightedNews = marketNews.items
    .slice()
    .sort((left, right) => {
      if (right.importanceScore !== left.importanceScore) {
        return right.importanceScore - left.importanceScore;
      }
      return right.publishedAt.localeCompare(left.publishedAt);
    })
    .slice(0, 2)
    .map((item) => `《${truncateText(item.title, 24)}》`)
    .join("、");

  return `近 ${DEFAULT_NEWS_LOOKBACK_DAYS} 天共纳入 ${marketNews.total} 条相关新闻${marketNews.truncated ? "（公开源截断）" : ""}；主题集中在 ${topicSummary}；地区分布以 ${regionSummary} 为主${highlightedNews ? `；高重要度线索：${highlightedNews}` : ""}`;
}

function buildNewsEvidenceHighlights(marketNews: FundMarketNewsQueryResponse | null) {
  if (!marketNews || marketNews.items.length === 0) {
    return [] as string[];
  }

  const highlights: string[] = [];
  const topicSummary = formatCountBreakdown(
    marketNews.stats.byTopic.map((item) => ({ label: item.topic, count: item.count })),
    "",
  );
  if (topicSummary) {
    highlights.push(`近 ${DEFAULT_NEWS_LOOKBACK_DAYS} 天外部扰动主要集中在 ${topicSummary}。`);
  }

  const topEvents = marketNews.items
    .slice()
    .sort((left, right) => {
      if (right.importanceScore !== left.importanceScore) {
        return right.importanceScore - left.importanceScore;
      }
      return right.publishedAt.localeCompare(left.publishedAt);
    })
    .slice(0, 2)
    .map((item) => `《${truncateText(item.title, 28)}》`);
  if (topEvents.length > 0) {
    highlights.push(`高重要度事件包括 ${topEvents.join("、")}。`);
  }

  const impactTagCounter = new Map<string, number>();
  marketNews.items.forEach((item) => {
    item.impactTags.forEach((tag) => {
      impactTagCounter.set(tag, (impactTagCounter.get(tag) || 0) + 1);
    });
  });
  const topImpactTags = Array.from(impactTagCounter.entries())
    .sort((left, right) => right[1] - left[1])
    .slice(0, 4)
    .map(([tag]) => tag);
  if (topImpactTags.length > 0) {
    highlights.push(`高频影响标签有 ${topImpactTags.join("、")}，需要和基金的持仓暴露一起看。`);
  }

  return highlights.slice(0, 3);
}

function buildPreparedToolContext(input: {
  horizon: string;
  fundAnalysis: FundAnalysisResponse;
  peerBenchmark: FundPeerBenchmarkResponse | null;
  tradePlan: FundTradePlanSnapshot | null;
  holdingBreadth: FundHoldingBreadthResponse | null;
  marketNews: FundMarketNewsQueryResponse | null;
  marketNewsSummary: string | null;
}) {
  const { fundAnalysis, peerBenchmark, tradePlan, holdingBreadth, marketNews } = input;
  const latest = fundAnalysis.trendAnalysis.latest;
  const returns = fundAnalysis.trendAnalysis.returns;
  const risk = fundAnalysis.trendAnalysis.risk;
  const topNews = marketNews?.items
    .slice()
    .sort((left, right) => {
      if (right.importanceScore !== left.importanceScore) {
        return right.importanceScore - left.importanceScore;
      }
      return right.publishedAt.localeCompare(left.publishedAt);
    })
    .slice(0, PREPARED_NEWS_ITEM_LIMIT)
    .map((item) => ({
      publishedAt: item.publishedAt,
      title: item.title,
      topic: item.topic,
      region: item.region,
      importanceScore: item.importanceScore,
      impactTags: item.impactTags,
      summary: truncateText(item.summary || item.title, 100),
    })) ?? [];

  return {
    analysisHorizon: input.horizon,
    preparedAt: new Date().toISOString(),
    fundContext: {
      code: fundAnalysis.fund.code,
      name: fundAnalysis.fund.name,
      latestNavDate: fundAnalysis.fund.latestNavDate,
      latestNav: fundAnalysis.fund.latestNav,
      estimatedNav: fundAnalysis.fund.estimatedNav,
      estimatedChangeRate: fundAnalysis.fund.estimatedChangeRate,
      category: fundAnalysis.screener?.category ?? null,
      sectorTags: fundAnalysis.screener?.sectorTags?.slice(0, 6) ?? [],
      themeTags: fundAnalysis.screener?.themeTags?.slice(0, 6) ?? [],
      localHolding: fundAnalysis.myHolding
        ? {
            positionAmount: fundAnalysis.myHolding.positionAmount,
            costNav: fundAnalysis.myHolding.costNav,
            currentProfitRate: fundAnalysis.myHolding.currentProfitRate,
            estimatedProfitRate: fundAnalysis.myHolding.estimatedProfitRate,
          }
        : null,
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
      bollPositionPercent: calculateBollingerPositionPercent(latest.nav, latest.bollLower, latest.bollUpper),
      return5d: returns.day5,
      return10d: returns.day10,
      return20d: returns.day20,
      performance: fundAnalysis.performance,
    },
    mediumLongTermTrend: {
      return60d: returns.day60,
      return120d: returns.day120,
      return250d: returns.day250,
      maxDrawdown30d: risk.maxDrawdown30d,
      maxDrawdown90d: risk.maxDrawdown90d,
      maxDrawdown1y: risk.maxDrawdown1y,
      volatility30d: risk.volatility30d,
      volatility90d: risk.volatility90d,
      volatility1y: risk.volatility1y,
      analysisWindowDays: fundAnalysis.trendAnalysis.windowDays,
      startDate: fundAnalysis.trendAnalysis.startDate,
      endDate: fundAnalysis.trendAnalysis.endDate,
    },
    topHoldings: fundAnalysis.stockHoldings.slice(0, 5).map((item) => ({
      name: item.name,
      navRatio: item.navRatio,
      changeRate: item.changeRate,
    })),
    holdingBreadth: holdingBreadth
      ? {
          totalHoldings: holdingBreadth.totalHoldings,
          positiveCount: holdingBreadth.positiveCount,
          negativeCount: holdingBreadth.negativeCount,
          averageChangeRate: holdingBreadth.averageChangeRate,
          concentrationTop3: holdingBreadth.concentrationTop3,
          concentrationTop5: holdingBreadth.concentrationTop5,
        }
      : null,
    peerBenchmark: peerBenchmark
      ? {
          peerBaseCount: peerBenchmark.peerBaseCount,
          percentile: peerBenchmark.percentile,
          peerSamples: peerBenchmark.peers.slice(0, 3).map((item) => ({
            code: item.code,
            name: item.name,
            category: item.category,
            similarityScore: item.similarityScore,
            return3m: item.metrics.return3m,
            return1y: item.metrics.return1y,
            maxDrawdown1y: item.metrics.maxDrawdown1y,
            volatility1y: item.metrics.volatility1y,
          })),
        }
      : null,
    tradePlan: tradePlan
      ? {
          holding: tradePlan.holding,
          sizingSuggestion: tradePlan.sizingSuggestion,
          planLevels: tradePlan.planLevels,
          observationSignals: tradePlan.observationSignals,
          riskFlags: tradePlan.riskFlags,
        }
      : null,
    marketNews: marketNews
      ? {
          startTime: marketNews.startTime,
          endTime: marketNews.endTime,
          total: marketNews.total,
          truncated: marketNews.truncated,
          stats: marketNews.stats,
          topNews,
        }
      : {
          unavailableReason: input.marketNewsSummary || "近期市场新闻暂未取到，请谨慎处理外部催化判断。",
        },
  };
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
    throw new Error("模型没有返回分析结果。");
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

function normalizeToolArguments(rawArguments: string | undefined) {
  if (!rawArguments) {
    return {};
  }

  try {
    return JSON.parse(rawArguments) as Record<string, unknown>;
  } catch {
    throw new Error(`工具参数解析失败：${rawArguments}`);
  }
}

function formatTrackedToolSummary(toolName: string, structuredContent: Record<string, unknown> | null, fallbackSummary: string) {
  if (toolName === "get_fund_market_news") {
    return buildMarketNewsDigest(structuredContent as FundMarketNewsQueryResponse | null, fallbackSummary);
  }

  return fallbackSummary;
}

export class FundAgentService {
  private readonly registry = createFinancialMcpRegistry();
  private readonly client = new OpenAI({
    apiKey: getRequiredEnvValue(["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "api_key"], "缺少 DeepSeek API Key，请在项目 .env 中配置。"),
    baseURL: getEnvValue(["DEEPSEEK_BASE_URL"], "https://api.deepseek.com") || "https://api.deepseek.com",
  });
  private readonly model = DEFAULT_MODEL;

  private async executeTrackedTool<T extends Record<string, unknown>>(
    toolName: string,
    input: Record<string, unknown>,
    toolTrace: AgentToolTrace[],
    toolOutputs: Map<string, Record<string, unknown> | null>,
    options?: { swallowError?: boolean },
  ): Promise<{ summary: string; structuredContent: T | null }> {
    try {
      const toolResult = await this.registry.executeTool(toolName, input);
      const structuredContent = toolResult.structuredContent && typeof toolResult.structuredContent === "object"
        ? (toolResult.structuredContent as T)
        : null;
      const summary = formatTrackedToolSummary(toolName, structuredContent as Record<string, unknown> | null, toolResult.summary);

      toolOutputs.set(toolName, structuredContent);
      toolTrace.push({
        toolName,
        summary,
      });

      return {
        summary,
        structuredContent,
      };
    } catch (error) {
      const summary = error instanceof Error ? `${toolName} 调用失败：${error.message}` : `${toolName} 调用失败。`;
      toolOutputs.set(toolName, null);
      toolTrace.push({
        toolName,
        summary,
      });
      if (options?.swallowError) {
        return {
          summary,
          structuredContent: null,
        };
      }
      throw error;
    }
  }

  async analyzeFund(request: FundAgentRequest): Promise<FundAgentAnalysisResponse> {
    const fundCode = normalizeFundCode(request.fundCode);
    const horizon = String(request.horizon || DEFAULT_HORIZON).trim() || DEFAULT_HORIZON;
    const userQuestion = String(request.userQuestion || "").trim();
    const promptAssets = await loadPromptAssets();
    const toolTrace: AgentToolTrace[] = [];
    const toolOutputs = new Map<string, Record<string, unknown> | null>();

    const fundAnalysisResult = await this.executeTrackedTool<FundAnalysisResponse>(
      "get_fund_analysis",
      { fundCode, historyDays: DEFAULT_ANALYSIS_HISTORY_DAYS },
      toolTrace,
      toolOutputs,
    );
    const fundAnalysis = fundAnalysisResult.structuredContent;
    if (!fundAnalysis) {
      throw new Error("基金基础分析数据为空，无法继续生成结论。");
    }

    let resolvedFundName: string | null = fundAnalysis.fund.name || null;
    const peerBenchmark = (
      await this.executeTrackedTool<FundPeerBenchmarkResponse>(
        "get_fund_peer_benchmark",
        { fundCode, limit: 5 },
        toolTrace,
        toolOutputs,
      )
    ).structuredContent;
    const tradePlan = (
      await this.executeTrackedTool<FundTradePlanSnapshot>(
        "get_fund_trade_plan",
        { fundCode },
        toolTrace,
        toolOutputs,
      )
    ).structuredContent;

    let holdingBreadth: FundHoldingBreadthResponse | null = null;
    if (fundAnalysis.stockHoldings.length > 0) {
      holdingBreadth = (
        await this.executeTrackedTool<FundHoldingBreadthResponse>(
          "get_fund_holding_breadth",
          { fundCode, topline: 10 },
          toolTrace,
          toolOutputs,
          { swallowError: true },
        )
      ).structuredContent;
    }

    const marketNewsArgs = buildFundNewsQueryArgs(fundAnalysis);
    const marketNewsResult = await this.executeTrackedTool<FundMarketNewsQueryResponse>(
      "get_fund_market_news",
      marketNewsArgs,
      toolTrace,
      toolOutputs,
      { swallowError: true },
    );
    const marketNews = marketNewsResult.structuredContent;
    const preparedContext = buildPreparedToolContext({
      horizon,
      fundAnalysis,
      peerBenchmark,
      tradePlan,
      holdingBreadth,
      marketNews,
      marketNewsSummary: marketNewsResult.summary,
    });

    const messages: Array<Record<string, unknown>> = [
      {
        role: "system",
        content: buildSystemPrompt(promptAssets.skill, promptAssets.reference),
      },
      {
        role: "system",
        content: [
          "以下是系统预抓的工具数据摘要，全部来自项目内 MCP 工具，你必须把它们纳入最终结论。",
          JSON.stringify(preparedContext, null, 2),
          "如需更细节，可以继续调用工具补充，但不能忽略这份摘要。",
        ].join("\n\n"),
      },
      {
        role: "user",
        content: buildUserPrompt({ fundCode, horizon, userQuestion }),
      },
    ];

    for (let round = 0; round < MAX_TOOL_ROUNDS; round += 1) {
      const completion = await this.client.chat.completions.create({
        model: this.model,
        temperature: 0.15,
        messages: messages as never,
        tools: this.registry.listOpenAiToolDefinitions() as never,
        tool_choice: "auto",
      });

      const message = completion.choices[0]?.message;
      const content = extractTextContent(message?.content ?? "");
      const toolCalls = (message as { tool_calls?: Array<Record<string, unknown>> } | undefined)?.tool_calls ?? [];

      if (!toolCalls.length) {
        const rawPayload = JSON.parse(extractJsonBlock(content));
        const parsedReport = finalizeReport(rawPayload, toolOutputs, horizon);
        const forecast = buildForecast(rawPayload, toolOutputs, parsedReport);

        return {
          runId: randomUUID(),
          fundCode,
          fundName: resolvedFundName,
          generatedAt: new Date().toISOString(),
          model: this.model,
          toolTrace,
          report: parsedReport,
          forecast,
        };
      }

      messages.push({
        role: "assistant",
        content,
        tool_calls: toolCalls,
      });

      for (const toolCall of toolCalls) {
        const functionPayload = (toolCall.function ?? {}) as { name?: string; arguments?: string };
        const toolName = String(functionPayload.name || "").trim();
        if (!toolName) {
          continue;
        }

        const toolResult = await this.executeTrackedTool<Record<string, unknown>>(
          toolName,
          normalizeToolArguments(functionPayload.arguments),
          toolTrace,
          toolOutputs,
        );
        if (toolName === "get_fund_analysis") {
          const candidateName = (toolResult.structuredContent as { fund?: { name?: string } } | null)?.fund?.name;
          resolvedFundName = typeof candidateName === "string" && candidateName.trim() ? candidateName.trim() : resolvedFundName;
        }

        messages.push({
          role: "tool",
          tool_call_id: toolCall.id,
          content: JSON.stringify({
            summary: toolResult.summary,
            structuredContent: toolResult.structuredContent ?? null,
          }),
        });
      }
    }

    throw new Error("基金分析 Agent 在工具调用阶段超过轮次上限，请稍后重试。");
  }
}
