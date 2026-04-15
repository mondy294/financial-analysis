import type { McpServer } from "@modelcontextprotocol/server";
import { z } from "zod";
import { getFundHoldingStocks, getRealtimeStockQuotes } from "../stock-service.js";

const stockInputSchema = z.object({
  code: z.string().regex(/^\d{6}$/, "股票代码必须是 6 位数字"),
  exchange: z.enum(["SH", "SZ", "BJ"]).optional(),
});

const realtimeQuoteInputSchema = z.object({
  stocks: z.array(stockInputSchema).min(1).max(50),
});

const fundHoldingInputSchema = z.object({
  fundCode: z.string().regex(/^\d{6}$/, "基金代码必须是 6 位数字"),
  topline: z.number().int().min(1).max(50).optional(),
});

export function registerStockTools(server: McpServer) {
  server.registerTool(
    "get_realtime_stock_quotes",
    {
      title: "批量股票实时行情",
      description: "批量查询股票最新价、涨跌额、涨跌幅，适合基金重仓股或自选股观察。",
      inputSchema: realtimeQuoteInputSchema,
    },
    async ({ stocks }: z.infer<typeof realtimeQuoteInputSchema>) => {
      try {
        const items = await getRealtimeStockQuotes(stocks);
        return {
          content: [{ type: "text", text: `已返回 ${items.length} 只股票的实时行情。` }],
          structuredContent: {
            total: items.length,
            items,
          },
        };
      } catch (error) {
        return {
          isError: true,
          content: [{ type: "text", text: error instanceof Error ? error.message : "股票实时行情查询失败。" }],
        };
      }
    },
  );

  server.registerTool(
    "get_fund_holding_stocks",
    {
      title: "基金持仓股与实时涨跌",
      description: "查询基金最新披露的持仓股票，并补齐这些股票当前的实时涨跌信息。",
      inputSchema: fundHoldingInputSchema,
    },
    async ({ fundCode, topline }: z.infer<typeof fundHoldingInputSchema>) => {
      try {
        const payload = await getFundHoldingStocks(fundCode, topline ?? 10);
        return {
          content: [{ type: "text", text: `已返回基金 ${fundCode} 最新披露的 ${payload.items.length} 只持仓股。` }],
          structuredContent: payload,
        };
      } catch (error) {
        return {
          isError: true,
          content: [{ type: "text", text: error instanceof Error ? error.message : "基金持仓股查询失败。" }],
        };
      }
    },
  );
}
