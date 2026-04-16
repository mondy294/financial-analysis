export type ChartRange = "1M" | "3M" | "6M" | "1Y" | "YTD" | "ALL";
export type ScreenerFundCategory = "主动" | "指数" | "纯债" | "固收+" | "QDII" | "FOF";
export type ScreenerRankingKey = "return1m" | "return3m" | "return1y" | "lowDrawdown" | "lowVolatility" | "value" | "core" | "aggressive";
export type ScreenerSortOrder = "asc" | "desc";

export type FundTrendPoint = {
  date: string;
  nav: number | null;
};

export type FundTrendIndicatorPoint = FundTrendPoint & {
  ma5: number | null;
  ma10: number | null;
  ma20: number | null;
  ma60: number | null;
  bollUpper: number | null;
  bollLower: number | null;
  bollWidth20: number | null;
};

export type FundTrendInsights = {
  latestNav: number | null;
  ma5: number | null;
  ma10: number | null;
  ma20: number | null;
  ma60: number | null;
  bollUpper: number | null;
  bollLower: number | null;
  bollWidth20: number | null;
  deviationFromMa20: number | null;
  deviationFromMa60: number | null;
  deviationFromCost: number | null;
  annualizedVolatility20d: number | null;
  maxDrawdown: number | null;
};

export type FundNavHistoryItem = {
  date: string;
  unitNav: number | null;
  cumulativeNav: number | null;
  dailyGrowthRate: number | null;
  purchaseStatus: string | null;
  redemptionStatus: string | null;
};

export type FundHoldingStock = {
  code: string;
  name: string;
  exchange: string | null;
  latestPrice: number | null;
  changeRate: number | null;
  changeAmount: number | null;
  navRatio: number | null;
  holdingSharesWan: number | null;
  holdingMarketValueWan: number | null;
};

export type FundPerformanceSummary = {
  oneWeek: number | null;
  oneMonth: number | null;
  threeMonths: number | null;
  sixMonths: number | null;
  oneYear: number | null;
  yearToDate: number | null;
  sinceInception: number | null;
  lowestRecentNav: number | null;
  highestRecentNav: number | null;
};

export type FundMeta = {
  code: string;
  name: string;
  latestNavDate: string;
  latestNav: number | null;
  latestCumulativeNav: number | null;
  latestDailyGrowthRate: number | null;
  estimatedNav: number | null;
  estimatedChangeRate: number | null;
  estimateTime: string | null;
  purchaseStatus: string | null;
  redemptionStatus: string | null;
  sourceRate: string | null;
  currentRate: string | null;
};

export type FundDetailResponse = {
  fund: FundMeta;
  performance: FundPerformanceSummary;
  navHistory: FundNavHistoryItem[];
  trend: FundTrendPoint[];
  stockHoldings: FundHoldingStock[];
  stockHoldingsReportDate: string | null;
};

export type FundUniverseMetrics = {
  return1w: number | null;
  return1m: number | null;
  return3m: number | null;
  return6m: number | null;
  return1y: number | null;
  returnYtd: number | null;
  returnSinceInception: number | null;
  maxDrawdown1y: number | null;
  volatility1y: number | null;
  feeRate: number | null;
  originalFeeRate: number | null;
  size: number | null;
  establishedYears: number | null;
  latestNav: number | null;
  latestDailyGrowthRate: number | null;
  estimatedChangeRate: number | null;
  canBuy: boolean;
  canAutoInvest: boolean;
};

export type FundUniverseScore = {
  total: number;
  return: number;
  stability: number;
  drawdown: number;
  fee: number;
  management: number;
  health: number;
};

export type FundUniverseItem = {
  code: string;
  name: string;
  pinyin: string;
  rawFundType: string | null;
  category: ScreenerFundCategory;
  sectorTags: string[];
  themeTags: string[];
  establishedDate: string | null;
  latestNavDate: string | null;
  metrics: FundUniverseMetrics;
  score: FundUniverseScore;
  rankingSignals: {
    value: number;
    core: number;
    aggressive: number;
  };
  scoreSummary: string;
  dataWarnings: string[];
};

export type ScreenerQueryPayload = {
  fundTypes?: ScreenerFundCategory[];
  sectors?: string[];
  themes?: string[];
  minReturn1m?: number | null;
  minReturn3m?: number | null;
  minReturn6m?: number | null;
  minReturn1y?: number | null;
  maxDrawdown1y?: number | null;
  maxVolatility1y?: number | null;
  maxFeeRate?: number | null;
  minSize?: number | null;
  maxSize?: number | null;
  minEstablishedYears?: number | null;
  autoInvestOnly?: boolean;
  ranking?: ScreenerRankingKey | null;
  sortBy?: string | null;
  sortOrder?: ScreenerSortOrder;
  page?: number;
  pageSize?: number;
};

export type ScreenerQueryResponse = {
  updatedAt: string | null;
  isStale: boolean;
  coverageNote: string;
  appliedRanking: ScreenerRankingKey | null;
  items: FundUniverseItem[];
  total: number;
  page: number;
  pageSize: number;
};

export type ScreenerOptionResponse = {
  updatedAt: string | null;
  isStale: boolean;
  coverageNote: string;
  fundTypes: ScreenerFundCategory[];
  sectors: string[];
  themes: string[];
  rankings: Array<{
    key: ScreenerRankingKey;
    label: string;
    description: string;
  }>;
};

export type ScreenerSectorSource = "topic" | "tag";

export type ScreenerSectorStat = {
  id: string;
  name: string;
  count: number;
  totalFundCount: number | null;
  group: string;
  source: ScreenerSectorSource;
};

export type ScreenerPreset = {
  id: string;
  name: string;
  query: ScreenerQueryPayload;
  createdAt: string;
  updatedAt: string;
};

export type WatchlistItem = {
  code: string;
  addedAt: string;
  detail: FundDetailResponse | null;
  error: string | null;
};

export type CompareItem = {
  code: string;
  addedAt: string;
  detail: FundDetailResponse | null;
  screener: FundUniverseItem | null;
  error: string | null;
};

export type HoldingItem = {
  code: string;
  status: string;
  holdingReturnRate: number | null;
  positionAmount: number | null;
  costNav: number | null;
  note: string;
  updatedAt: string;
  detail: FundDetailResponse | null;
  error: string | null;
};

export type HoldingDraft = {
  code: string;
  status: string;
  holdingReturnRate: number | null;
  positionAmount: number | null;
  costNav: number | null;
  note: string;
};

export type AgentToolTrace = {
  toolName: string;
  summary: string;
};

export type FundAgentTrendOutlook = "偏多" | "中性" | "偏谨慎" | "无法判断";
export type FundAgentActionTag = "观望为主" | "分批布局" | "持有待跟踪" | "谨慎减仓";

export type FundAgentReport = {
  horizon: string;
  outlook: FundAgentTrendOutlook;
  confidence: number;
  summary: string;
  actionTag: FundAgentActionTag;
  actionAdvice: string;
  suitableFor: string;
  unsuitableFor: string;
  reasoning: string[];
  risks: string[];
  watchItems: string[];
  disclaimer: string;
};

export type FundAgentAnalysisResponse = {
  runId: string;
  fundCode: string;
  fundName: string | null;
  generatedAt: string;
  model: string;
  toolTrace: AgentToolTrace[];
  report: FundAgentReport;
};
