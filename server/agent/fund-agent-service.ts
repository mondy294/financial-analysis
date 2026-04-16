import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import OpenAI from "openai";
import { z } from "zod";
import { getRequiredEnvValue, getEnvValue } from "../env.js";
import { createFinancialMcpRegistry } from "../mcp/registry.js";
import type { AgentToolTrace, FundAgentAnalysisResponse, FundAgentReport, FundTradePlanLevel } from "../types.js";

const DEFAULT_MODEL = getEnvValue(["DEEPSEEK_MODEL"], "deepseek-reasoner") || "deepseek-reasoner";

const DEFAULT_HORIZON = "未来 1-3 个月";
const MAX_TOOL_ROUNDS = 6;

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

function normalizeStringList(value: unknown) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }

  if (typeof value === "string") {
    return value
      .split(/\r?\n|；|;/)
      .map((item) => item.replace(/^[\-•\d.\s、]+/, "").trim())
      .filter(Boolean);
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
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : fallback;
}

function pickList(value: unknown, fallback: string[], minimum: number, maximum: number) {
  const primary = normalizeStringList(value);
  const merged = primary.length >= minimum ? primary : fallback;
  return merged.slice(0, maximum).filter(Boolean);
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

  const signal = latest?.signal;
  if (typeof signal === "string") {
    reasons.push(`趋势结构：当前更接近${signal}。`);
  }

  const biasToMa20 = normalizeNullableNumber(latest?.biasToMa20);
  if (typeof biasToMa20 === "number") {
    reasons.push(`净值相对 MA20 乖离约 ${biasToMa20.toFixed(2)}%，说明当前离中期均线并不远。`);
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

  return reasons.slice(0, 6);
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
    "请明确区分：趋势判断、操作建议、风险提示、待观察指标、交易计划阈值。",
    "如果证据互相冲突，允许给出中性或无法判断，而不是硬凑单边结论。",
    "如果用户没有本地持仓，不要写成仓位管理结论，要偏向观察/分批。",
    "只要用户需要‘跌到多少加仓 / 反弹到多少减仓 / 现在该怎么做’这类计划，你必须调用 get_fund_trade_plan，并把其中的关键阈值转成结构化结论。",
    "最终只输出合法 JSON，不要输出 Markdown，不要输出代码块。",
    "JSON 必须严格包含这些字段：horizon,outlook,confidence,recentWeekSummary,recentWeekDrivers,summary,actionTag,actionAdvice,holdingContext,positionInstruction,positionSizing,planSummary,executionRules,planLevels,reEvaluationTriggers,suitableFor,unsuitableFor,reasoning,risks,watchItems,disclaimer。",
    "confidence 取 0-100 的整数。",
    "outlook 只能是：偏多 / 中性 / 偏谨慎 / 无法判断。",
    "actionTag 只能是：观望为主 / 分批布局 / 持有待跟踪 / 谨慎减仓。",
    "planLevels 必须给出 3-6 个关键价位，至少包含一个加仓相关价位和一个风控线；nav 与 relativeToLatest 使用数字或 null。",
    "executionRules 必须写成可以执行的句子，例如‘若净值跌到 X 以下但未破位，则...’。",
    "disclaimer 必须明确表达“仅供研究辅助，不构成投资建议”。",
    "以下是你的 Skill：",
    skill,
    "以下是你的 Reference：",
    reference,
  ].join("\n\n");
}

function buildUserPrompt(input: { fundCode: string; horizon: string; userQuestion: string }) {
  return [
    `请分析基金 ${input.fundCode}。`,
    `目标周期：${input.horizon}。`,
    `用户补充问题：${input.userQuestion || "请先解释最近一周变化、再分析未来走势，并给出当下操作建议。"}`,
    "至少先获取基金基础分析、同类对标和交易计划阈值；若有股票持仓，尽量补充持仓股广度。",
    "请先说明最近一周发生了什么，再解释变化的可能原因，最后给出未来 1-3 个月判断。",
    "如果存在本地持仓，请结合当前持仓金额、成本净值和组合占比，给出更具体的仓位动作与幅度范围。",
    "请明确回答：现在应该做什么、跌到什么净值附近可以考虑加仓、反弹到什么净值附近更适合减仓、什么条件出现就需要重新评估。",
    "输出时不要出现任何多余字段。",
  ].join("\n");
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

export class FundAgentService {
  private readonly registry = createFinancialMcpRegistry();
  private readonly client = new OpenAI({
    apiKey: getRequiredEnvValue(["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "api_key"], "缺少 DeepSeek API Key，请在项目 .env 中配置。"),
    baseURL: getEnvValue(["DEEPSEEK_BASE_URL"], "https://api.deepseek.com") || "https://api.deepseek.com",
  });
  private readonly model = DEFAULT_MODEL;

  async analyzeFund(request: FundAgentRequest): Promise<FundAgentAnalysisResponse> {
    const fundCode = normalizeFundCode(request.fundCode);
    const horizon = String(request.horizon || DEFAULT_HORIZON).trim() || DEFAULT_HORIZON;
    const userQuestion = String(request.userQuestion || "请分析未来走势并给出当下操作建议。").trim();
    const promptAssets = await loadPromptAssets();
    const toolTrace: AgentToolTrace[] = [];
    const toolOutputs = new Map<string, Record<string, unknown> | null>();
    let resolvedFundName: string | null = null;

    const messages: Array<Record<string, unknown>> = [
      {
        role: "system",
        content: buildSystemPrompt(promptAssets.skill, promptAssets.reference),
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
        const parsedReport = finalizeReport(JSON.parse(extractJsonBlock(content)), toolOutputs, horizon);

        return {
          runId: randomUUID(),
          fundCode,
          fundName: resolvedFundName,
          generatedAt: new Date().toISOString(),
          model: this.model,
          toolTrace,
          report: parsedReport,
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

        const toolResult = await this.registry.executeTool(toolName, normalizeToolArguments(functionPayload.arguments));
        toolOutputs.set(
          toolName,
          toolResult.structuredContent && typeof toolResult.structuredContent === "object"
            ? (toolResult.structuredContent as Record<string, unknown>)
            : null,
        );
        if (toolName === "get_fund_analysis") {
          const candidateName = (toolResult.structuredContent as { fund?: { name?: string } } | undefined)?.fund?.name;
          resolvedFundName = typeof candidateName === "string" && candidateName.trim() ? candidateName.trim() : resolvedFundName;
        }

        toolTrace.push({
          toolName,
          summary: toolResult.summary,
        });

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
