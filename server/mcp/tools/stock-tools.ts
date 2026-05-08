import { z } from "zod";
import { getFundHoldingStocks, getRealtimeStockQuotes } from "../../stock-service.js";
import type { FinancialMcpContext } from "../core/context.js";
import { BaseMcpTool } from "../core/tool.js";

const stockInputSchema = z.object({
  code: z.string().regex(/^\d{6}$/, "股票代码必须是 6 位数字"),
  exchange: z.enum(["SH", "SZ", "BJ"]).optional(),
});

export class RealtimeStockQuotesTool extends BaseMcpTool<typeof RealtimeStockQuotesTool.schema> {
  static readonly schema = z.object({
    stocks: z.array(stockInputSchema).min(1).max(50),
  });

  readonly name = "get_realtime_stock_quotes";
  readonly title = "批量股票实时行情";
  readonly description = "批量查询股票最新价、开高低收、成交量和成交额，适合基金重仓股或自选股观察。";
  readonly inputSchema = RealtimeStockQuotesTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute({ stocks }: z.infer<typeof RealtimeStockQuotesTool.schema>) {
    const items = await getRealtimeStockQuotes(stocks);
    return {
      summary: `已返回 ${items.length} 只股票的实时行情。`,
      structuredContent: {
        total: items.length,
        items,
      },
    };
  }
}

export class FundHoldingStocksTool extends BaseMcpTool<typeof FundHoldingStocksTool.schema> {
  static readonly schema = z.object({
    fundCode: z.string().regex(/^\d{6}$/, "基金代码必须是 6 位数字"),
    topline: z.number().int().min(1).max(50).optional(),
  });

  readonly name = "get_fund_holding_stocks";
  readonly title = "基金持仓股与实时涨跌";
  readonly description = "查询基金最新披露的持仓股票，并补齐这些股票当前的实时涨跌信息。";
  readonly inputSchema = FundHoldingStocksTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute({ fundCode, topline }: z.infer<typeof FundHoldingStocksTool.schema>) {
    const payload = await getFundHoldingStocks(fundCode, topline ?? 10);
    return {
      summary: `已返回基金 ${fundCode} 最新披露的 ${payload.items.length} 只持仓股。`,
      structuredContent: payload,
    };
  }
}

export class StockAnalysisTool extends BaseMcpTool<typeof StockAnalysisTool.schema> {
  static readonly schema = z.object({
    stockCode: z.string().regex(/^\d{6}$/, "股票代码必须是 6 位数字"),
    historyDays: z.number().int().min(20).max(1000).optional(),
  });

  readonly name = "get_stock_analysis";
  readonly title = "股票分析视图";
  readonly description = "通过股票代码获取开高低收、K 线、均线、布林带、阶段收益和风险指标。";
  readonly inputSchema = StockAnalysisTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute({ stockCode, historyDays }: z.infer<typeof StockAnalysisTool.schema>) {
    const payload = await this.context.stockAnalysisService.getStockAnalysis(stockCode, { historyDays });
    return {
      summary: `已生成股票 ${stockCode} 的分析结果，包含 K 线、均线、布林带与风险指标。`,
      structuredContent: payload,
    };
  }
}

export class StockTradePlanTool extends BaseMcpTool<typeof StockTradePlanTool.schema> {
  static readonly schema = z.object({
    stockCode: z.string().regex(/^\d{6}$/, "股票代码必须是 6 位数字"),
  });

  readonly name = "get_stock_trade_plan";
  readonly title = "股票交易计划阈值";
  readonly description = "结合 K 线形态、均线位置和风险波动，返回股票的观察位、试探位、减仓位和风控线。";
  readonly inputSchema = StockTradePlanTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute({ stockCode }: z.infer<typeof StockTradePlanTool.schema>) {
    const payload = await this.context.stockResearchService.getTradePlanSnapshot(stockCode);
    return {
      summary: `已返回股票 ${stockCode} 的交易计划阈值，共整理 ${payload.planLevels.length} 个关键价位。`,
      structuredContent: payload,
    };
  }
}
