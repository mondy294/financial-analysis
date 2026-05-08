import { z } from "zod";
import { queryFundMarketNews } from "../../news-service.js";
import type { FinancialMcpContext } from "../core/context.js";
import { BaseMcpTool } from "../core/tool.js";

const regionEnum = z.enum(["国内", "海外"]);
const topicEnum = z.enum(["焦点", "基金", "全球股市", "商品", "外汇", "债券", "地区", "央行", "经济数据"]);

const baseNewsSchema = z.object({
  startTime: z.string().min(1, "开始时间不能为空"),
  endTime: z.string().min(1, "结束时间不能为空"),
  regions: z.array(regionEnum).max(2).optional(),
  topics: z.array(topicEnum).max(9).optional(),
  keywords: z.array(z.string().min(1).max(30)).max(12).optional(),
  limit: z.number().int().min(10).max(500).optional(),
});

export class FundMarketNewsTool extends BaseMcpTool<typeof FundMarketNewsTool.schema> {
  static readonly schema = baseNewsSchema;

  readonly name = "get_fund_market_news";
  readonly title = "基金相关市场新闻";
  readonly description = "按时间段查询可能影响基金的国内外市场新闻，覆盖焦点、基金、股市、商品、外汇、债券、地区、央行和经济数据栏目。";
  readonly inputSchema = FundMarketNewsTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute(input: z.infer<typeof FundMarketNewsTool.schema>) {
    const payload = await queryFundMarketNews(input);
    return {
      summary: payload.truncated
        ? `已返回 ${payload.total} 条基金相关市场新闻（结果已按公开源能力截断）。`
        : `已返回 ${payload.total} 条基金相关市场新闻。`,
      structuredContent: payload,
    };
  }
}

export class StockMarketNewsTool extends BaseMcpTool<typeof StockMarketNewsTool.schema> {
  static readonly schema = baseNewsSchema;

  readonly name = "get_stock_market_news";
  readonly title = "股票相关市场新闻";
  readonly description = "按时间段查询可能影响个股与市场情绪的国内外新闻，可结合股票名称、代码等关键词过滤。";
  readonly inputSchema = StockMarketNewsTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute(input: z.infer<typeof StockMarketNewsTool.schema>) {
    const payload = await queryFundMarketNews(input);
    return {
      summary: payload.truncated
        ? `已返回 ${payload.total} 条股票相关市场新闻（结果已按公开源能力截断）。`
        : `已返回 ${payload.total} 条股票相关市场新闻。`,
      structuredContent: payload,
    };
  }
}
