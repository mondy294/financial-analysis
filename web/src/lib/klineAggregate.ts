import type { ChartBar } from "@/components/KlineChart";

export type KlinePeriod = "day" | "week" | "month";

function weekKey(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00`);
  // ISO week: Thursday-based year + week number
  const tmp = new Date(d);
  tmp.setDate(tmp.getDate() + 3 - ((tmp.getDay() + 6) % 7));
  const week1 = new Date(tmp.getFullYear(), 0, 4);
  const week =
    1 +
    Math.round(
      ((tmp.getTime() - week1.getTime()) / 86400000 - 3 + ((week1.getDay() + 6) % 7)) / 7,
    );
  return `${tmp.getFullYear()}-W${String(week).padStart(2, "0")}`;
}

function monthKey(isoDate: string): string {
  return isoDate.slice(0, 7);
}

/** 将日 K 聚合成周 K / 月 K（trade_date 取区间末日）。 */
export function aggregateKline(bars: ChartBar[], period: KlinePeriod): ChartBar[] {
  if (period === "day" || bars.length === 0) return bars;

  const keyFn = period === "week" ? weekKey : monthKey;
  const groups = new Map<string, ChartBar[]>();
  for (const b of bars) {
    const k = keyFn(b.trade_date);
    const list = groups.get(k);
    if (list) list.push(b);
    else groups.set(k, [b]);
  }

  const out: ChartBar[] = [];
  for (const list of groups.values()) {
    const first = list[0];
    const last = list[list.length - 1];
    let high = first.high;
    let low = first.low;
    let volume = 0;
    for (const b of list) {
      if (b.high > high) high = b.high;
      if (b.low < low) low = b.low;
      volume += b.volume;
    }
    out.push({
      trade_date: last.trade_date,
      open: first.open,
      high,
      low,
      close: last.close,
      volume,
    });
  }
  return out;
}

export function defaultVisibleCount(period: KlinePeriod): number {
  if (period === "week") return 52;
  if (period === "month") return 36;
  // 日 K 默认约 40 根，避免窗口过长把蜡烛压扁
  return 40;
}
