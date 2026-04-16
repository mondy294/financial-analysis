import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import OpenAI from "openai";
import { z } from "zod";
import { getRequiredEnvValue, getEnvValue } from "../env.js";
import { createFinancialMcpRegistry } from "../mcp/registry.js";
import type { AgentToolTrace, FundAgentAnalysisResponse, FundAgentReport } from "../types.js";

const DEFAULT_MODEL = getEnvValue(["DEEPSEEK_MODEL"], "deepseek-chat") || "deepseek-chat";
const DEFAULT_HORIZON = "未来 1-3 个月";
const MAX_TOOL_ROUNDS = 6;

const agentReportSchema = z.object({
  horizon: z.string().min(1),
  outlook: z.enum(["偏多", "中性", "偏谨慎", "无法判断"]),
  confidence: z.number().int().min(0).max(100),
  summary: z.string().min(8),
  actionTag: z.enum(["观望为主", "分批布局", "持有待跟踪", "谨慎减仓"]),
  actionAdvice: z.string().min(8),
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

function normalizeReportPayload(value: unknown) {
  const source = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  return {
    ...source,
    reasoning: normalizeStringList(source.reasoning),
    risks: normalizeStringList(source.risks),
    watchItems: normalizeStringList(source.watchItems),
  };
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
    "请明确区分：趋势判断、操作建议、风险提示、待观察指标。",
    "如果证据互相冲突，允许给出中性或无法判断，而不是硬凑单边结论。",
    "如果用户没有本地持仓，不要写成仓位管理结论，要偏向观察/分批。",
    "最终只输出合法 JSON，不要输出 Markdown，不要输出代码块。",
    "JSON 必须严格包含这些字段：horizon,outlook,confidence,summary,actionTag,actionAdvice,suitableFor,unsuitableFor,reasoning,risks,watchItems,disclaimer。",
    "confidence 取 0-100 的整数。",
    "outlook 只能是：偏多 / 中性 / 偏谨慎 / 无法判断。",
    "actionTag 只能是：观望为主 / 分批布局 / 持有待跟踪 / 谨慎减仓。",
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
    `用户补充问题：${input.userQuestion || "请分析未来走势并给出当下操作建议。"}`,
    "至少先获取基金基础分析和同类对标；若有股票持仓，尽量补充持仓股广度。",
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
        const parsedReport = agentReportSchema.parse(normalizeReportPayload(JSON.parse(extractJsonBlock(content)))) as FundAgentReport;

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
