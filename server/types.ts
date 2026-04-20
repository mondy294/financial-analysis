export type FundTrendPoint = {
  date: string;
  nav: number | null;
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

export type StockQuoteSnapshot = {
  code: string;
  name: string | null;
  exchange: string | null;
  secId: string;
  latestPrice: number | null;
  changeRate: number | null;
  changeAmount: number | null;
};

export type FundHoldingStocksLookupResponse = {
  fundCode: string;
  reportDate: string | null;
  items: FundHoldingStock[];
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

export type PersistedWatchlistItem = {
  code: string;
  addedAt: string;
};

export type PersistedHoldingItem = {
  code: string;
  status: string;
  holdingReturnRate: number | null;
  positionAmount: number | null;
  costNav: number | null;
  note: string;
  updatedAt: string;
};

export type PersistedCompareItem = {
  code: string;
  addedAt: string;
};

export type PersistedModelProviderSettings = {
  baseUrl: string | null;
  apiKey: string | null;
};

export type ModelProviderSettingsResponse = {
  baseUrl: string;
  model: string;
  apiKeyConfigured: boolean;
  apiKeyMasked: string | null;
  hasCustomBaseUrl: boolean;
  hasCustomApiKey: boolean;
};

export type ModelProviderSettingsUpdate = {
  baseUrl?: string | null;
  apiKey?: string | null;
};

export type ScreenerFundCategory = "主动" | "指数" | "纯债" | "固收+" | "QDII" | "FOF";
export type ScreenerRankingKey = "return1m" | "return3m" | "return1y" | "lowDrawdown" | "lowVolatility" | "value" | "core" | "aggressive";
export type ScreenerSortOrder = "asc" | "desc";

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

export type FundUniverseCacheFile = {
  updatedAt: string | null;
  coverageNote: string;
  items: FundUniverseItem[];
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

export type ScreenerQueryResult = {
  updatedAt: string | null;
  isStale: boolean;
  coverageNote: string;
  appliedRanking: ScreenerRankingKey | null;
  items: FundUniverseItem[];
  total: number;
  page: number;
  pageSize: number;
};

export type ScreenerOptionsResponse = {
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

export type ScreenerSectorCacheItem = ScreenerSectorStat & {
  fundCodes: string[];
};

export type ScreenerSectorCacheFile = {
  updatedAt: string | null;
  universeUpdatedAt: string | null;
  coverageNote: string;
  items: ScreenerSectorCacheItem[];
};

export type PersistedScreenerPreset = {
  id: string;
  name: string;
  query: ScreenerQueryPayload;
  createdAt: string;
  updatedAt: string;
};

export type CollectionFile<T> = {
  items: T[];
};

export type EnrichedWatchlistItem = PersistedWatchlistItem & {
  detail: FundDetailResponse | null;
  error: string | null;
};

export type EnrichedHoldingItem = PersistedHoldingItem & {
  detail: FundDetailResponse | null;
  error: string | null;
};

export type EnrichedCompareItem = PersistedCompareItem & {
  detail: FundDetailResponse | null;
  screener: FundUniverseItem | null;
  error: string | null;
};

export type FundTrendSignal = "多头排列" | "空头排列" | "震荡整理" | "数据不足";

export type FundTrendAnalysisPoint = {
  date: string;
  nav: number;
  rangeReturn: number;
  ma5: number | null;
  ma10: number | null;
  ma20: number | null;
  ma60: number | null;
  bollUpper: number | null;
  bollLower: number | null;
  bollWidth20: number | null;
};

export type FundTrendAnalysis = {
  windowDays: number;
  startDate: string | null;
  endDate: string | null;
  points: FundTrendAnalysisPoint[];
  latest: {
    date: string;
    nav: number;
    ma5: number | null;
    ma10: number | null;
    ma20: number | null;
    ma60: number | null;
    bollUpper: number | null;
    bollLower: number | null;
    bollWidth20: number | null;
    biasToMa10: number | null;
    biasToMa20: number | null;
    biasToMa60: number | null;
    signal: FundTrendSignal;
  };
  returns: {
    range: number | null;
    day5: number | null;
    day10: number | null;
    day20: number | null;
    day60: number | null;
    day120: number | null;
    day250: number | null;
  };
  risk: {
    maxDrawdown30d: number | null;
    maxDrawdown90d: number | null;
    maxDrawdown1y: number | null;
    volatility30d: number | null;
    volatility90d: number | null;
    volatility1y: number | null;
  };
};

export type FundHoldingSnapshot = {
  code: string;
  fundName: string | null;
  status: string;
  holdingReturnRate: number | null;
  positionAmount: number | null;
  costNav: number | null;
  note: string;
  updatedAt: string;
  positionShares: number | null;
  latestNav: number | null;
  latestNavDate: string | null;
  estimatedNav: number | null;
  estimateTime: string | null;
  currentMarketValue: number | null;
  estimatedMarketValue: number | null;
  currentProfitAmount: number | null;
  currentProfitRate: number | null;
  estimatedProfitAmount: number | null;
  estimatedProfitRate: number | null;
};

export type FundHoldingPortfolioResponse = {
  items: FundHoldingSnapshot[];
  summary: {
    holdingsCount: number;
    totalPositionAmount: number | null;
    totalCurrentMarketValue: number | null;
    totalEstimatedMarketValue: number | null;
    totalCurrentProfitAmount: number | null;
    totalEstimatedProfitAmount: number | null;
  };
};

export type FundAnalysisResponse = {
  fund: FundMeta;
  performance: FundPerformanceSummary;
  navHistory: FundNavHistoryItem[];
  stockHoldings: FundHoldingStock[];
  stockHoldingsReportDate: string | null;
  trendAnalysis: FundTrendAnalysis;
  screener: FundUniverseItem | null;
  myHolding: FundHoldingSnapshot | null;
};

export type FundPeerBenchmarkPeer = {
  code: string;
  name: string;
  category: ScreenerFundCategory;
  rawFundType: string | null;
  sectorTags: string[];
  themeTags: string[];
  scoreTotal: number;
  similarityScore: number;
  metrics: FundUniverseMetrics;
};

export type FundPeerBenchmarkResponse = {
  fundCode: string;
  updatedAt: string | null;
  peerBaseCount: number;
  subject: FundUniverseItem | null;
  percentile: {
    return1m: number | null;
    return3m: number | null;
    return1y: number | null;
    maxDrawdown1y: number | null;
    volatility1y: number | null;
    feeRate: number | null;
    scoreTotal: number | null;
  } | null;
  peers: FundPeerBenchmarkPeer[];
};

export type FundHoldingBreadthResponse = {
  fundCode: string;
  reportDate: string | null;
  totalHoldings: number;
  positiveCount: number;
  negativeCount: number;
  flatCount: number;
  averageChangeRate: number | null;
  concentrationTop3: number | null;
  concentrationTop5: number | null;
  strongestStocks: FundHoldingStock[];
  weakestStocks: FundHoldingStock[];
};

export type FundTradePlanLevelKind = "观察确认位" | "试探加仓位" | "分批加仓位" | "减仓位" | "风控线";

export type FundTradePlanLevel = {
  kind: FundTradePlanLevelKind;
  nav: number | null;
  relativeToLatest: number | null;
  reference: string;
  condition: string;
  action: string;
  reason: string;
};

export type FundTradePlanSnapshot = {
  fundCode: string;
  fundName: string | null;
  category: ScreenerFundCategory | null;
  signal: FundTrendSignal;
  latestNav: number | null;
  estimatedNav: number | null;
  estimatedChangeRate: number | null;
  ma10: number | null;
  ma20: number | null;
  ma60: number | null;
  biasToMa20: number | null;
  biasToMa60: number | null;
  holding: {
    hasHolding: boolean;
    status: string | null;
    positionAmount: number | null;
    costNav: number | null;
    currentProfitRate: number | null;
    estimatedProfitRate: number | null;
    portfolioPositionRatio: number | null;
  };
  sizingSuggestion: {
    currentActionBias: string;
    addOnDip: string;
    addOnBreakout: string;
    reduceOnWeakness: string;
    initialProbe: string;
  };
  planLevels: FundTradePlanLevel[];
  observationSignals: string[];
  riskFlags: string[];
};

export type AgentToolTrace = {
  toolName: string;
  summary: string;
};

export type FundAgentTrendOutlook = "偏多" | "中性" | "偏谨慎" | "无法判断";
export type FundAgentActionTag = "观望为主" | "分批布局" | "持有待跟踪" | "谨慎减仓";
export type FundAgentForecastVolatility = "低" | "中" | "高";
export type FundAgentForecastPathStyle = "震荡上行" | "高位震荡" | "区间震荡" | "先抑后扬" | "先扬后抑" | "震荡下行";

export type FundAgentReport = {
  horizon: string;
  outlook: FundAgentTrendOutlook;
  confidence: number;
  recentWeekSummary: string;
  recentWeekDrivers: string[];
  summary: string;
  actionTag: FundAgentActionTag;
  actionAdvice: string;
  holdingContext: string;
  positionInstruction: string;
  positionSizing: string;
  planSummary: string;
  executionRules: string[];
  planLevels: FundTradePlanLevel[];
  reEvaluationTriggers: string[];
  suitableFor: string;
  unsuitableFor: string;
  reasoning: string[];
  risks: string[];
  watchItems: string[];
  disclaimer: string;
};

export type FundAgentForecastPoint = {
  date: string;
  nav: number;
  returnRate: number;
};

export type FundAgentForecastScenario = {
  id: string;
  label: string;
  probability: number;
  summary: string;
  trigger: string;
  targetReturn: number;
  targetNav: number;
  volatility: FundAgentForecastVolatility;
  pathStyle: FundAgentForecastPathStyle;
  points: FundAgentForecastPoint[];
};

export type FundAgentForecast = {
  horizon: string;
  baseDate: string;
  baseNav: number;
  stepDays: number;
  scenarios: FundAgentForecastScenario[];
};

export type FundAgentAnalysisResponse = {
  runId: string;
  fundCode: string;
  fundName: string | null;
  generatedAt: string;
  model: string;
  toolTrace: AgentToolTrace[];
  report: FundAgentReport;
  forecast: FundAgentForecast | null;
};

export type PersistedFundAgentAnalysis = FundAgentAnalysisResponse & {
  updatedAt: string;
};

export type FundAgentBatchAnalysisItemStatus = "success" | "failed";

export type FundAgentBatchAnalysisItem = {
  fundCode: string;
  fundName: string | null;
  status: FundAgentBatchAnalysisItemStatus;
  generatedAt: string | null;
  updatedAt: string | null;
  error: string | null;
};

export type FundAgentBatchAnalysisResult = {
  scope: "watchlist";
  horizon: string;
  userQuestion: string | null;
  total: number;
  succeeded: number;
  failed: number;
  startedAt: string;
  finishedAt: string;
  durationMs: number;
  items: FundAgentBatchAnalysisItem[];
};

export type FundMarketNewsRegion = "国内" | "海外" | "综合";
export type FundMarketNewsTopic = "焦点" | "基金" | "全球股市" | "商品" | "外汇" | "债券" | "地区" | "央行" | "经济数据";

export type FundMarketNewsItem = {
  id: string;
  title: string;
  summary: string;
  publishedAt: string;
  source: string;
  detailUrl: string | null;
  topic: FundMarketNewsTopic;
  region: FundMarketNewsRegion;
  feedKey: string;
  feedLabel: string;
  importanceScore: number;
  impactTags: string[];
  relatedStocks: Array<{
    code: string;
    name: string;
  }>;
};

export type FundMarketNewsFeedStat = {
  feedKey: string;
  feedLabel: string;
  topic: FundMarketNewsTopic;
  region: FundMarketNewsRegion;
  pagesFetched: number;
  matchedCount: number;
  earliestMatchedAt: string | null;
  latestMatchedAt: string | null;
  truncated: boolean;
};

export type FundMarketNewsQueryResponse = {
  startTime: string;
  endTime: string;
  limit: number;
  keywords: string[];
  regions: FundMarketNewsRegion[];
  topics: FundMarketNewsTopic[];
  total: number;
  truncated: boolean;
  coverageNote: string;
  feedStats: FundMarketNewsFeedStat[];
  stats: {
    byTopic: Array<{
      topic: string;
      count: number;
    }>;
    byRegion: Array<{
      region: string;
      count: number;
    }>;
  };
  items: FundMarketNewsItem[];
};
