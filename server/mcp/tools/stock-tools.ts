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
  readonly description = "批量查询股票最新价、涨跌额、涨跌幅，适合基金重仓股或自选股观察。";
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
