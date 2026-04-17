import {
  calculateAnnualizedVolatility,
  calculateBiasRate,
  calculateBollingerBandsSeries,
  calculateMaxDrawdown,
  calculateMovingAverageSeries,
  calculateRangeReturn,
  calculateTradingDayReturn,
  roundNullable,
  sliceTrendByDays,
} from "./analysis-utils.js";
import { getFundPerformance } from "./fund-service.js";
import { PortfolioService } from "./portfolio-service.js";
import { getUniverseItemByCode } from "./screener-service.js";
import type { FundAnalysisResponse, FundTrendAnalysis, FundTrendAnalysisPoint, FundTrendPoint, FundTrendSignal } from "./types.js";

function normalizeFundCode(code: string) {
  const cleanCode = String(code || "").trim();
  if (!/^\d{6}$/.test(cleanCode)) {
    throw new Error("基金编号必须是 6 位数字。");
  }
  return cleanCode;
}

function detectSignal(latestNav: number, ma5: number | null, ma10: number | null, ma20: number | null): FundTrendSignal {
  if ([ma5, ma10, ma20].some((value) => typeof value !== "number")) {
    return "数据不足";
  }

  if (latestNav >= (ma5 as number) && (ma5 as number) >= (ma10 as number) && (ma10 as number) >= (ma20 as number)) {
    return "多头排列";
  }

  if (latestNav <= (ma5 as number) && (ma5 as number) <= (ma10 as number) && (ma10 as number) <= (ma20 as number)) {
    return "空头排列";
  }

  return "震荡整理";
}

function buildTrendAnalysis(points: FundTrendPoint[], historyDays: number): FundTrendAnalysis {
  const ma5Map = calculateMovingAverageSeries(points, 5);
  const ma10Map = calculateMovingAverageSeries(points, 10);
  const ma20Map = calculateMovingAverageSeries(points, 20);
  const ma60Map = calculateMovingAverageSeries(points, 60);
  const boll20Map = calculateBollingerBandsSeries(points, 20);
  const windowPoints = sliceTrendByDays(points, historyDays);
  const startNav = windowPoints[0]?.nav ?? null;

  const analysisPoints: FundTrendAnalysisPoint[] = windowPoints.map((point) => {
    const boll20 = boll20Map.get(point.date);

    return {
      date: point.date,
      nav: point.nav,
      rangeReturn: typeof startNav === "number" && startNav !== 0 ? roundNullable(((point.nav - startNav) / startNav) * 100, 2) ?? 0 : 0,
      ma5: ma5Map.get(point.date) ?? null,
      ma10: ma10Map.get(point.date) ?? null,
      ma20: ma20Map.get(point.date) ?? null,
      ma60: ma60Map.get(point.date) ?? null,
      bollUpper: boll20?.upper ?? null,
      bollLower: boll20?.lower ?? null,
      bollWidth20: boll20?.width ?? null,
    };
  });

  const latest = analysisPoints.at(-1);
  if (!latest) {
    throw new Error("基金走势数据为空，暂时无法分析。");
  }

  return {
    windowDays: historyDays,
    startDate: analysisPoints[0]?.date ?? null,
    endDate: latest.date,
    points: analysisPoints,
    latest: {
      date: latest.date,
      nav: latest.nav,
      ma5: latest.ma5,
      ma10: latest.ma10,
      ma20: latest.ma20,
      ma60: latest.ma60,
      bollUpper: latest.bollUpper,
      bollLower: latest.bollLower,
      bollWidth20: latest.bollWidth20,
      biasToMa10: calculateBiasRate(latest.nav, latest.ma10),
      biasToMa20: calculateBiasRate(latest.nav, latest.ma20),
      biasToMa60: calculateBiasRate(latest.nav, latest.ma60),
      signal: detectSignal(latest.nav, latest.ma5, latest.ma10, latest.ma20),
    },
    returns: {
      range: calculateRangeReturn(windowPoints),
      day5: calculateTradingDayReturn(points, 5),
      day10: calculateTradingDayReturn(points, 10),
      day20: calculateTradingDayReturn(points, 20),
      day60: calculateTradingDayReturn(points, 60),
      day120: calculateTradingDayReturn(points, 120),
      day250: calculateTradingDayReturn(points, 250),
    },
    risk: {
      maxDrawdown30d: calculateMaxDrawdown(sliceTrendByDays(points, 30)),
      maxDrawdown90d: calculateMaxDrawdown(sliceTrendByDays(points, 90)),
      maxDrawdown1y: calculateMaxDrawdown(sliceTrendByDays(points, 365)),
      volatility30d: calculateAnnualizedVolatility(sliceTrendByDays(points, 30)),
      volatility90d: calculateAnnualizedVolatility(sliceTrendByDays(points, 90)),
      volatility1y: calculateAnnualizedVolatility(sliceTrendByDays(points, 365)),
    },
  };
}

export class FundAnalysisService {
  constructor(private readonly portfolioService = new PortfolioService()) {}

  async getFundAnalysis(code: string, options?: { historyDays?: number }): Promise<FundAnalysisResponse> {
    const cleanCode = normalizeFundCode(code);
    const historyDays = Math.min(Math.max(Number(options?.historyDays ?? 120), 20), 750);
    const detail = await getFundPerformance(cleanCode);
    const [myHolding, screener] = await Promise.all([
      this.portfolioService.getHoldingSnapshot(cleanCode),
      getUniverseItemByCode(cleanCode).catch(() => null),
    ]);

    return {
      fund: detail.fund,
      performance: detail.performance,
      navHistory: detail.navHistory,
      stockHoldings: detail.stockHoldings,
      stockHoldingsReportDate: detail.stockHoldingsReportDate,
      trendAnalysis: buildTrendAnalysis(detail.trend, historyDays),
      screener,
      myHolding,
    };
  }
}
