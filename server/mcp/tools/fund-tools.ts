import { z } from "zod";
import { getScreenerOptions, getSectorFunds, getSectorStats, queryFundUniverse, refreshFundUniverseCache } from "../../screener-service.js";
import type { FinancialMcpContext } from "../core/context.js";
import { BaseMcpTool } from "../core/tool.js";

const fundTypeEnum = z.enum(["主动", "指数", "纯债", "固收+", "QDII", "FOF"]);
const rankingEnum = z.enum(["return1m", "return3m", "return1y", "lowDrawdown", "lowVolatility", "value", "core", "aggressive"]);
const sortOrderEnum = z.enum(["asc", "desc"]);

export class FundAnalysisTool extends BaseMcpTool<typeof FundAnalysisTool.schema> {
  static readonly schema = z.object({
    fundCode: z.string().regex(/^\d{6}$/, "基金代码必须是 6 位数字"),
    historyDays: z.number().int().min(20).max(750).optional(),
  });

  readonly name = "get_fund_analysis";
  readonly title = "基金分析视图";
  readonly description = "通过基金编号获取净值、均线、阶段收益、波动回撤、重仓股和我的本地持仓信息。";
  readonly inputSchema = FundAnalysisTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute({ fundCode, historyDays }: z.infer<typeof FundAnalysisTool.schema>) {
    const payload = await this.context.fundAnalysisService.getFundAnalysis(fundCode, { historyDays });
    return {
      summary: `已生成基金 ${fundCode} 的分析结果，含净值走势、均线、风险指标与本地持仓信息。`,
      structuredContent: payload,
    };
  }
}

export class FundPeerBenchmarkTool extends BaseMcpTool<typeof FundPeerBenchmarkTool.schema> {
  static readonly schema = z.object({
    fundCode: z.string().regex(/^\d{6}$/, "基金代码必须是 6 位数字"),
    limit: z.number().int().min(1).max(10).optional(),
  });

  readonly name = "get_fund_peer_benchmark";
  readonly title = "基金同类对标";
  readonly description = "返回同类基金中的相对分位、最相似可比基金列表和关键收益/回撤/波动位置。";
  readonly inputSchema = FundPeerBenchmarkTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute({ fundCode, limit }: z.infer<typeof FundPeerBenchmarkTool.schema>) {
    const payload = await this.context.fundResearchService.getPeerBenchmark(fundCode, limit ?? 5);
    return {
      summary: payload.subject
        ? `已返回基金 ${fundCode} 的同类对标结果，基于 ${payload.peerBaseCount} 只同类基金计算。`
        : `基金 ${fundCode} 暂未进入本地基金池缓存，未能生成同类对标。`,
      structuredContent: payload,
    };
  }
}

export class FundHoldingBreadthTool extends BaseMcpTool<typeof FundHoldingBreadthTool.schema> {
  static readonly schema = z.object({
    fundCode: z.string().regex(/^\d{6}$/, "基金代码必须是 6 位数字"),
    topline: z.number().int().min(1).max(20).optional(),
  });

  readonly name = "get_fund_holding_breadth";
  readonly title = "基金重仓股强弱广度";
  readonly description = "汇总基金重仓股的上涨/下跌数量、平均涨跌幅、集中度以及最强最弱个股。";
  readonly inputSchema = FundHoldingBreadthTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute({ fundCode, topline }: z.infer<typeof FundHoldingBreadthTool.schema>) {
    const payload = await this.context.fundResearchService.getHoldingBreadth(fundCode, topline ?? 10);
    return {
      summary: `已返回基金 ${fundCode} 最近披露持仓的广度结果，共覆盖 ${payload.totalHoldings} 只股票。`,
      structuredContent: payload,
    };
  }
}

export class MyFundHoldingTool extends BaseMcpTool<typeof MyFundHoldingTool.schema> {
  static readonly schema = z.object({
    fundCode: z.string().regex(/^\d{6}$/, "基金代码必须是 6 位数字"),
  });

  readonly name = "get_my_fund_holding";
  readonly title = "查询我的基金持仓";
  readonly description = "按基金编号查询本地保存的当前持仓，并补充当前净值、估值和盈亏测算。";
  readonly inputSchema = MyFundHoldingTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute({ fundCode }: z.infer<typeof MyFundHoldingTool.schema>) {
    const holding = await this.context.portfolioService.getHoldingSnapshot(fundCode);
    return {
      summary: holding ? `已返回基金 ${fundCode} 的本地持仓信息。` : `本地持仓中未找到基金 ${fundCode}。`,
      structuredContent: {
        fundCode,
        holding,
      },
    };
  }
}

export class ListMyFundHoldingsTool extends BaseMcpTool<typeof ListMyFundHoldingsTool.schema> {
  static readonly schema = z.object({});

  readonly name = "list_my_fund_holdings";
  readonly title = "列出我的全部基金持仓";
  readonly description = "返回本地保存的全部基金持仓及组合汇总，适合做组合回顾和后续分析。";
  readonly inputSchema = ListMyFundHoldingsTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute(_: z.infer<typeof ListMyFundHoldingsTool.schema>) {
    const payload = await this.context.portfolioService.getPortfolioResponse();
    return {
      summary: `已返回 ${payload.items.length} 条本地基金持仓记录。`,
      structuredContent: payload,
    };
  }
}

export class FundScreenerOptionsTool extends BaseMcpTool<typeof FundScreenerOptionsTool.schema> {
  static readonly schema = z.object({});

  readonly name = "get_fund_screener_options";
  readonly title = "基金筛选选项";
  readonly description = "获取基金筛选器可用的基金类型、行业概念、主题和排行榜定义。";
  readonly inputSchema = FundScreenerOptionsTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute(_: z.infer<typeof FundScreenerOptionsTool.schema>) {
    const payload = await getScreenerOptions();
    return {
      summary: "已返回基金筛选器配置。",
      structuredContent: payload,
    };
  }
}

export class QueryFundUniverseTool extends BaseMcpTool<typeof QueryFundUniverseTool.schema> {
  static readonly schema = z.object({
    fundTypes: z.array(fundTypeEnum).max(6).optional(),
    sectors: z.array(z.string().min(1)).max(20).optional(),
    themes: z.array(z.string().min(1)).max(20).optional(),
    minReturn1m: z.number().nullable().optional(),
    minReturn3m: z.number().nullable().optional(),
    minReturn6m: z.number().nullable().optional(),
    minReturn1y: z.number().nullable().optional(),
    maxDrawdown1y: z.number().nullable().optional(),
    maxVolatility1y: z.number().nullable().optional(),
    maxFeeRate: z.number().nullable().optional(),
    minSize: z.number().nullable().optional(),
    maxSize: z.number().nullable().optional(),
    minEstablishedYears: z.number().nullable().optional(),
    autoInvestOnly: z.boolean().optional(),
    ranking: rankingEnum.nullable().optional(),
    sortBy: z.string().nullable().optional(),
    sortOrder: sortOrderEnum.optional(),
    page: z.number().int().min(1).optional(),
    pageSize: z.number().int().min(1).max(100).optional(),
  });

  readonly name = "query_fund_universe";
  readonly title = "基金池筛选查询";
  readonly description = "按收益、回撤、波动、费率、主题等条件筛选基金池，返回适合进一步分析的候选。";
  readonly inputSchema = QueryFundUniverseTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute(input: z.infer<typeof QueryFundUniverseTool.schema>) {
    const payload = await queryFundUniverse(input);
    return {
      summary: `已筛出 ${payload.total} 只基金，当前返回第 ${payload.page} 页。`,
      structuredContent: payload,
    };
  }
}

export class FundSectorsTool extends BaseMcpTool<typeof FundSectorsTool.schema> {
  static readonly schema = z.object({});

  readonly name = "get_fund_sectors";
  readonly title = "基金行业概念统计";
  readonly description = "获取基金池中有数据的行业、概念和策略标签统计。";
  readonly inputSchema = FundSectorsTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute(_: z.infer<typeof FundSectorsTool.schema>) {
    const items = await getSectorStats();
    return {
      summary: `已返回 ${items.length} 个行业/概念/标签统计项。`,
      structuredContent: {
        total: items.length,
        items,
      },
    };
  }
}

export class SectorFundsTool extends BaseMcpTool<typeof SectorFundsTool.schema> {
  static readonly schema = z.object({
    sector: z.string().min(1, "板块名称不能为空"),
    ranking: rankingEnum.optional(),
  });

  readonly name = "get_sector_funds";
  readonly title = "按行业概念查看基金";
  readonly description = "根据行业、概念或标签获取对应基金列表，可结合排行榜方式排序。";
  readonly inputSchema = SectorFundsTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute({ sector, ranking }: z.infer<typeof SectorFundsTool.schema>) {
    const payload = await getSectorFunds(sector, ranking ?? "value");
    return {
      summary: `已返回板块 ${sector} 下的 ${payload.total} 只基金。`,
      structuredContent: payload,
    };
  }
}

export class RefreshFundUniverseCacheTool extends BaseMcpTool<typeof RefreshFundUniverseCacheTool.schema> {
  static readonly schema = z.object({});

  readonly name = "refresh_fund_universe_cache";
  readonly title = "刷新基金池缓存";
  readonly description = "主动刷新基金池与行业概念缓存，适合在分析前拉取较新的候选数据。";
  readonly inputSchema = RefreshFundUniverseCacheTool.schema;

  constructor(context: FinancialMcpContext) {
    super(context);
  }

  protected async execute(_: z.infer<typeof RefreshFundUniverseCacheTool.schema>) {
    const payload = await refreshFundUniverseCache();
    return {
      summary: `基金池缓存已刷新，共 ${payload.items.length} 只候选基金。`,
      structuredContent: {
        updatedAt: payload.updatedAt,
        total: payload.items.length,
        coverageNote: payload.coverageNote,
      },
    };
  }
}
