import type { ChartRange, FundTrendIndicatorPoint, FundTrendInsights, FundTrendPoint } from "../types";

export const RANGE_OPTIONS: Array<{ key: ChartRange; label: string }> = [
  { key: "1M", label: "近 1 月" },
  { key: "3M", label: "近 3 月" },
  { key: "6M", label: "近 6 月" },
  { key: "1Y", label: "近 1 年" },
  { key: "YTD", label: "年初至今" },
  { key: "ALL", label: "全部" },
];

const percentFormatter = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const navFormatter = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});

const currencyFormatter = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  const numeric = Number(value);
  return `${numeric > 0 ? "+" : ""}${percentFormatter.format(numeric)}%`;
}

export function formatNav(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return navFormatter.format(Number(value));
}

export function formatAmount(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return `¥${currencyFormatter.format(Number(value))}`;
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "--";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function signedClass(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "neutral";
  }

  const numeric = Number(value);
  if (numeric > 0) {
    return "positive";
  }
  if (numeric < 0) {
    return "negative";
  }
  return "neutral";
}

function subtractFromDate(dateText: string, range: ChartRange) {
  const date = new Date(`${dateText}T00:00:00`);

  switch (range) {
    case "1M":
      date.setMonth(date.getMonth() - 1);
      return date;
    case "3M":
      date.setMonth(date.getMonth() - 3);
      return date;
    case "6M":
      date.setMonth(date.getMonth() - 6);
      return date;
    case "1Y":
      date.setFullYear(date.getFullYear() - 1);
      return date;
    case "YTD":
      return new Date(`${dateText.slice(0, 4)}-01-01T00:00:00`);
    case "ALL":
    default:
      return null;
  }
}

function toTimestamp(dateText: string) {
  return new Date(`${dateText}T00:00:00`).getTime();
}

function normalizeTrendPoints(points: FundTrendPoint[]) {
  return [...points]
    .filter((point) => point.date)
    .sort((left, right) => toTimestamp(left.date) - toTimestamp(right.date))
    .map((point) => ({
      date: point.date,
      nav: point.nav !== null && Number.isFinite(point.nav) ? Number(point.nav) : null,
    }));
}

function getValidWindow(values: Array<number | null>, period: number, endIndex: number): number[] | null {
  if (endIndex + 1 < period) {
    return null;
  }

  const slice = values.slice(endIndex - period + 1, endIndex + 1);
  if (slice.some((value) => value === null)) {
    return null;
  }

  return slice as number[];
}

function calculateMovingAverage(values: Array<number | null>, period: number, endIndex: number) {
  const window = getValidWindow(values, period, endIndex);
  if (!window) {
    return null;
  }

  const sum = window.reduce<number>((total, value) => total + value, 0);
  return Number((sum / period).toFixed(4));
}

function calculateBollingerBands(values: Array<number | null>, period: number, endIndex: number, multiplier = 2) {
  const window = getValidWindow(values, period, endIndex);
  if (!window) {
    return {
      upper: null,
      lower: null,
      width: null,
    };
  }

  const mean = window.reduce((total, value) => total + value, 0) / window.length;
  const variance = window.reduce((total, value) => total + (value - mean) ** 2, 0) / window.length;
  const deviation = Math.sqrt(variance);
  const upper = mean + deviation * multiplier;
  const lower = mean - deviation * multiplier;
  const width = mean === 0 ? null : ((upper - lower) / mean) * 100;

  return {
    upper: Number(upper.toFixed(4)),
    lower: Number(lower.toFixed(4)),
    width: width === null ? null : Number(width.toFixed(2)),
  };
}

function calculateAnnualizedVolatility(points: FundTrendIndicatorPoint[], period: number) {
  if (points.length < 2) {
    return null;
  }

  const relevantPoints = points.filter((point) => point.nav !== null);
  const returns: number[] = [];

  for (let index = 1; index < relevantPoints.length; index += 1) {
    const previous = relevantPoints[index - 1]?.nav;
    const current = relevantPoints[index]?.nav;

    if (!previous || !current || previous === 0) {
      continue;
    }

    returns.push((current - previous) / previous);
  }

  const sample = returns.slice(-period);
  if (sample.length < 2) {
    return null;
  }

  const mean = sample.reduce((total, value) => total + value, 0) / sample.length;
  const variance = sample.reduce((total, value) => total + (value - mean) ** 2, 0) / (sample.length - 1);
  const volatility = Math.sqrt(variance) * Math.sqrt(252) * 100;

  return Number(volatility.toFixed(2));
}

function calculateMaxDrawdown(points: FundTrendIndicatorPoint[]) {
  const navValues = points.map((point) => point.nav).filter((value): value is number => value !== null);
  if (navValues.length < 2) {
    return null;
  }

  let peak = navValues[0];
  let maxDrawdown = 0;

  for (const nav of navValues) {
    peak = Math.max(peak, nav);
    if (peak === 0) {
      continue;
    }

    const drawdown = ((nav - peak) / peak) * 100;
    maxDrawdown = Math.min(maxDrawdown, drawdown);
  }

  return Number(maxDrawdown.toFixed(2));
}

export function buildTrendIndicators(points: FundTrendPoint[]): FundTrendIndicatorPoint[] {
  const normalizedPoints = normalizeTrendPoints(points);
  const navSeries = normalizedPoints.map((point) => point.nav);

  return normalizedPoints.map((point, index) => {
    const ma5 = calculateMovingAverage(navSeries, 5, index);
    const ma10 = calculateMovingAverage(navSeries, 10, index);
    const ma20 = calculateMovingAverage(navSeries, 20, index);
    const ma60 = calculateMovingAverage(navSeries, 60, index);
    const bollinger = calculateBollingerBands(navSeries, 20, index);

    return {
      ...point,
      ma5,
      ma10,
      ma20,
      ma60,
      bollUpper: bollinger.upper,
      bollLower: bollinger.lower,
      bollWidth20: bollinger.width,
    };
  });
}

export function filterTrendByRange<T extends { date: string }>(points: T[], range: ChartRange) {
  if (points.length <= 1) {
    return points;
  }

  const targetDate = subtractFromDate(points.at(-1)?.date ?? points[0].date, range);
  if (!targetDate) {
    return points;
  }

  const targetTimestamp = targetDate.getTime();
  const filtered = points.filter((point) => toTimestamp(point.date) >= targetTimestamp);

  return filtered.length >= 2 ? filtered : points.slice(-Math.min(points.length, 30));
}

export function calculateRangeReturn(points: Array<{ nav: number | null }>) {
  if (points.length < 2) {
    return null;
  }

  const first = points[0]?.nav;
  const last = points.at(-1)?.nav;

  if (!first || !last || first === 0) {
    return null;
  }

  return Number((((last - first) / first) * 100).toFixed(2));
}

export function calculateTrendInsights(points: FundTrendIndicatorPoint[], costNav?: number | null): FundTrendInsights {
  const latestPoint = [...points].reverse().find((point) => point.nav !== null) ?? null;
  const latestNav = latestPoint?.nav ?? null;
  const ma20 = latestPoint?.ma20 ?? null;
  const ma60 = latestPoint?.ma60 ?? null;
  const normalizedCostNav = costNav !== null && costNav !== undefined && Number.isFinite(costNav) ? Number(costNav) : null;

  const deviationFromMa20 = latestNav !== null && ma20 !== null && ma20 !== 0 ? Number((((latestNav - ma20) / ma20) * 100).toFixed(2)) : null;
  const deviationFromMa60 = latestNav !== null && ma60 !== null && ma60 !== 0 ? Number((((latestNav - ma60) / ma60) * 100).toFixed(2)) : null;
  const deviationFromCost = latestNav !== null && normalizedCostNav !== null && normalizedCostNav !== 0
    ? Number((((latestNav - normalizedCostNav) / normalizedCostNav) * 100).toFixed(2))
    : null;

  return {
    latestNav,
    ma5: latestPoint?.ma5 ?? null,
    ma10: latestPoint?.ma10 ?? null,
    ma20,
    ma60,
    bollUpper: latestPoint?.bollUpper ?? null,
    bollLower: latestPoint?.bollLower ?? null,
    bollWidth20: latestPoint?.bollWidth20 ?? null,
    deviationFromMa20,
    deviationFromMa60,
    deviationFromCost,
    annualizedVolatility20d: calculateAnnualizedVolatility(points, 20),
    maxDrawdown: calculateMaxDrawdown(points),
  };
}
