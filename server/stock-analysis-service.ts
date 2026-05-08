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
import { getStockDetail } from "./stock-service.js";
import type {
  FundTrendPoint,
  StockAnalysisResponse,
  StockDetailResponse,
  StockKLinePoint,
  StockPerformanceSummary,
  StockTrendAnalysis,
  StockTrendAnalysisPoint,
  StockTrendSignal,
} from "./types.js";

function normalizeStockCode(code: string) {
  const cleanCode = String(code || "").trim();
  if (!/^\d{6}$/.test(cleanCode)) {
    throw new Error("股票代码必须是 6 位数字。");
  }
  return cleanCode;
}

function toCloseTrend(points: StockKLinePoint[]): FundTrendPoint[] {
  return points.map((item) => ({
    date: item.date,
    nav: item.close,
  }));
}

function detectSignal(latestClose: number, ma5: number | null, ma10: number | null, ma20: number | null): StockTrendSignal {
  if ([ma5, ma10, ma20].some((value) => typeof value !== "number")) {
    return "数据不足";
  }

  if (latestClose >= (ma5 as number) && (ma5 as number) >= (ma10 as number) && (ma10 as number) >= (ma20 as number)) {
    return "多头排列";
  }

  if (latestClose <= (ma5 as number) && (ma5 as number) <= (ma10 as number) && (ma10 as number) <= (ma20 as number)) {
    return "空头排列";
  }

  return "震荡整理";
}

function calculateCandleBodyChangeRate(open: number | null, close: number | null) {
  if (typeof open !== "number" || !Number.isFinite(open) || open === 0) {
    return null;
  }
  if (typeof close !== "number" || !Number.isFinite(close)) {
    return null;
  }

  return roundNullable(((close - open) / open) * 100, 2);
}

function calculateUpperShadowRate(open: number | null, close: number | null, high: number | null) {
  if (typeof open !== "number" || !Number.isFinite(open) || open === 0) {
    return null;
  }
  if (typeof close !== "number" || !Number.isFinite(close) || typeof high !== "number" || !Number.isFinite(high)) {
    return null;
  }

  return roundNullable(((high - Math.max(open, close)) / open) * 100, 2);
}

function calculateLowerShadowRate(open: number | null, close: number | null, low: number | null) {
  if (typeof open !== "number" || !Number.isFinite(open) || open === 0) {
    return null;
  }
  if (typeof close !== "number" || !Number.isFinite(close) || typeof low !== "number" || !Number.isFinite(low)) {
    return null;
  }

  return roundNullable(((Math.min(open, close) - low) / open) * 100, 2);
}

function calculateRangeReturnFromDate(points: FundTrendPoint[], startDate: string) {
  const filtered = points.filter((item) => item.date >= startDate);
  return calculateRangeReturn(filtered);
}

function buildPerformanceSummary(detail: StockDetailResponse): StockPerformanceSummary {
  const closeTrend = toCloseTrend(detail.kline);
  const latestTradeDate = detail.stock.latestTradeDate;
  const ytdStartDate = `${latestTradeDate.slice(0, 4)}-01-01`;

  return {
    oneWeek: calculateTradingDayReturn(closeTrend, 5),
    oneMonth: calculateTradingDayReturn(closeTrend, 20),
    threeMonths: calculateTradingDayReturn(closeTrend, 60),
    sixMonths: calculateTradingDayReturn(closeTrend, 120),
    oneYear: calculateTradingDayReturn(closeTrend, 250),
    yearToDate: calculateRangeReturnFromDate(closeTrend, ytdStartDate),
    sinceInception: calculateRangeReturn(closeTrend),
    lowestRecentClose: (() => {
      const recent = sliceTrendByDays(closeTrend, 30).map((item) => item.nav).filter((value): value is number => typeof value === "number");
      return recent.length > 0 ? Math.min(...recent) : null;
    })(),
    highestRecentClose: (() => {
      const recent = sliceTrendByDays(closeTrend, 30).map((item) => item.nav).filter((value): value is number => typeof value === "number");
      return recent.length > 0 ? Math.max(...recent) : null;
    })(),
  };
}

function buildTrendAnalysis(points: StockKLinePoint[], historyDays: number): StockTrendAnalysis {
  const closeTrend = toCloseTrend(points);
  const ma5Map = calculateMovingAverageSeries(closeTrend, 5);
  const ma10Map = calculateMovingAverageSeries(closeTrend, 10);
  const ma20Map = calculateMovingAverageSeries(closeTrend, 20);
  const ma60Map = calculateMovingAverageSeries(closeTrend, 60);
  const boll20Map = calculateBollingerBandsSeries(closeTrend, 20);
  const windowPoints = sliceTrendByDays(closeTrend, historyDays);
  const visibleDates = new Set(windowPoints.map((item) => item.date));
  const visibleKline = points.filter((item) => visibleDates.has(item.date));
  const startClose = visibleKline[0]?.close ?? null;

  const analysisPoints: StockTrendAnalysisPoint[] = visibleKline.map((point) => {
    const boll20 = boll20Map.get(point.date);
    return {
      date: point.date,
      open: point.open ?? point.close ?? 0,
      close: point.close ?? 0,
      high: point.high ?? point.close ?? point.open ?? 0,
      low: point.low ?? point.close ?? point.open ?? 0,
      volume: point.volume,
      amount: point.amount,
      amplitude: point.amplitude,
      turnoverRate: point.turnoverRate,
      rangeReturn:
        typeof startClose === "number" && startClose !== 0 && typeof point.close === "number"
          ? roundNullable(((point.close - startClose) / startClose) * 100, 2) ?? 0
          : 0,
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
    throw new Error("股票 K 线数据为空，暂时无法分析。");
  }

  return {
    windowDays: historyDays,
    startDate: analysisPoints[0]?.date ?? null,
    endDate: latest.date,
    points: analysisPoints,
    latest: {
      date: latest.date,
      open: latest.open,
      close: latest.close,
      high: latest.high,
      low: latest.low,
      amplitude: latest.amplitude,
      turnoverRate: latest.turnoverRate,
      ma5: latest.ma5,
      ma10: latest.ma10,
      ma20: latest.ma20,
      ma60: latest.ma60,
      bollUpper: latest.bollUpper,
      bollLower: latest.bollLower,
      bollWidth20: latest.bollWidth20,
      biasToMa10: calculateBiasRate(latest.close, latest.ma10),
      biasToMa20: calculateBiasRate(latest.close, latest.ma20),
      biasToMa60: calculateBiasRate(latest.close, latest.ma60),
      dailyChangeRate: visibleKline.at(-1)?.changeRate ?? null,
      bodyChangeRate: calculateCandleBodyChangeRate(latest.open, latest.close),
      upperShadowRate: calculateUpperShadowRate(latest.open, latest.close, latest.high),
      lowerShadowRate: calculateLowerShadowRate(latest.open, latest.close, latest.low),
      signal: detectSignal(latest.close, latest.ma5, latest.ma10, latest.ma20),
    },
    returns: {
      range: calculateRangeReturn(windowPoints),
      day5: calculateTradingDayReturn(closeTrend, 5),
      day10: calculateTradingDayReturn(closeTrend, 10),
      day20: calculateTradingDayReturn(closeTrend, 20),
      day60: calculateTradingDayReturn(closeTrend, 60),
      day120: calculateTradingDayReturn(closeTrend, 120),
      day250: calculateTradingDayReturn(closeTrend, 250),
    },
    risk: {
      maxDrawdown30d: calculateMaxDrawdown(sliceTrendByDays(closeTrend, 30)),
      maxDrawdown90d: calculateMaxDrawdown(sliceTrendByDays(closeTrend, 90)),
      maxDrawdown1y: calculateMaxDrawdown(sliceTrendByDays(closeTrend, 365)),
      volatility30d: calculateAnnualizedVolatility(sliceTrendByDays(closeTrend, 30)),
      volatility90d: calculateAnnualizedVolatility(sliceTrendByDays(closeTrend, 90)),
      volatility1y: calculateAnnualizedVolatility(sliceTrendByDays(closeTrend, 365)),
    },
  };
}

export class StockAnalysisService {
  async getStockAnalysis(code: string, options?: { historyDays?: number; klineLimit?: number }): Promise<StockAnalysisResponse> {
    const cleanCode = normalizeStockCode(code);
    const historyDays = Math.min(Math.max(Number(options?.historyDays ?? 180), 20), 1000);
    const detail = await getStockDetail(cleanCode, { klineLimit: options?.klineLimit ?? 1200 });

    return {
      stock: detail.stock,
      performance: buildPerformanceSummary(detail),
      kline: detail.kline,
      trendAnalysis: buildTrendAnalysis(detail.kline, historyDays),
    };
  }
}
