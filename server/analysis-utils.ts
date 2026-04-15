import type { FundTrendPoint } from "./types.js";

const TRADING_DAYS_PER_YEAR = 252;

function roundNumber(value: number, digits: number) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

export function toTimestamp(dateText: string) {
  return new Date(`${dateText}T00:00:00`).getTime();
}

export function toValidTrendPoints(points: FundTrendPoint[]) {
  return points.filter((point): point is FundTrendPoint & { nav: number } => typeof point.nav === "number" && Number.isFinite(point.nav));
}

export function sliceTrendByDays(points: FundTrendPoint[], days?: number | null) {
  const valid = toValidTrendPoints(points);
  if (!days || days <= 0 || valid.length === 0) {
    return valid;
  }

  const latestDate = valid.at(-1)?.date;
  if (!latestDate) {
    return valid;
  }

  const thresholdDate = new Date(`${latestDate}T00:00:00`);
  thresholdDate.setDate(thresholdDate.getDate() - days);
  const threshold = thresholdDate.getTime();
  const sliced = valid.filter((point) => toTimestamp(point.date) >= threshold);
  return sliced.length >= 2 ? sliced : valid;
}

export function calculateMovingAverageSeries(points: FundTrendPoint[], period: number) {
  const valid = toValidTrendPoints(points);
  const result = new Map<string, number | null>();
  const queue: number[] = [];
  let sum = 0;

  for (const point of valid) {
    queue.push(point.nav);
    sum += point.nav;

    if (queue.length > period) {
      sum -= queue.shift() ?? 0;
    }

    result.set(point.date, queue.length >= period ? roundNumber(sum / period, 4) : null);
  }

  return result;
}

export function calculateTradingDayReturn(points: FundTrendPoint[], periodsBack: number) {
  const valid = toValidTrendPoints(points);
  if (valid.length <= periodsBack) {
    return null;
  }

  const latest = valid.at(-1);
  const base = valid.at(-(periodsBack + 1));
  if (!latest || !base || base.nav === 0) {
    return null;
  }

  return roundNumber(((latest.nav - base.nav) / base.nav) * 100, 2);
}

export function calculateRangeReturn(points: FundTrendPoint[]) {
  const valid = toValidTrendPoints(points);
  if (valid.length < 2) {
    return null;
  }

  const start = valid[0];
  const latest = valid.at(-1);
  if (!start || !latest || start.nav === 0) {
    return null;
  }

  return roundNumber(((latest.nav - start.nav) / start.nav) * 100, 2);
}

export function calculateAnnualizedVolatility(points: FundTrendPoint[]) {
  const relevant = toValidTrendPoints(points);
  if (relevant.length < 2) {
    return null;
  }

  const returns: number[] = [];
  for (let index = 1; index < relevant.length; index += 1) {
    const previous = relevant[index - 1]?.nav;
    const current = relevant[index]?.nav;

    if (!previous || !current || previous === 0) {
      continue;
    }

    returns.push((current - previous) / previous);
  }

  if (returns.length < 2) {
    return null;
  }

  const mean = returns.reduce((total, item) => total + item, 0) / returns.length;
  const variance = returns.reduce((total, item) => total + (item - mean) ** 2, 0) / (returns.length - 1);
  return roundNumber(Math.sqrt(variance) * Math.sqrt(TRADING_DAYS_PER_YEAR) * 100, 2);
}

export function calculateMaxDrawdown(points: FundTrendPoint[]) {
  const navValues = toValidTrendPoints(points).map((point) => point.nav);
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

  return roundNumber(maxDrawdown, 2);
}

export function sumNumbers(values: Array<number | null | undefined>) {
  const numbers = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  return numbers.length ? roundNumber(numbers.reduce((total, value) => total + value, 0), 2) : null;
}

export function divideNumbers(numerator: number | null | undefined, denominator: number | null | undefined, digits = 2) {
  if (typeof numerator !== "number" || !Number.isFinite(numerator)) {
    return null;
  }
  if (typeof denominator !== "number" || !Number.isFinite(denominator) || denominator === 0) {
    return null;
  }

  return roundNumber(numerator / denominator, digits);
}

export function roundNullable(value: number | null | undefined, digits = 2) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }

  return roundNumber(value, digits);
}
