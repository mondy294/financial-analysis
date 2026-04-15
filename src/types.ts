export type ChartRange = "1M" | "3M" | "6M" | "1Y" | "YTD" | "ALL";

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
};

export type WatchlistItem = {
  code: string;
  addedAt: string;
  detail: FundDetailResponse | null;
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
