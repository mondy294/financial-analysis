import type { ChartRange, FundTrendPoint } from "../types";

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

export function filterTrendByRange(points: FundTrendPoint[], range: ChartRange) {
  if (points.length <= 1) {
    return points;
  }

  const targetDate = subtractFromDate(points.at(-1)?.date ?? points[0].date, range);
  if (!targetDate) {
    return points;
  }

  const targetTimestamp = targetDate.getTime();
  const filtered = points.filter((point) => {
    const pointTime = new Date(`${point.date}T00:00:00`).getTime();
    return pointTime >= targetTimestamp;
  });

  return filtered.length >= 2 ? filtered : points.slice(-Math.min(points.length, 30));
}

export function calculateRangeReturn(points: FundTrendPoint[]) {
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
