import type { EventStatsRun } from "@/api/client";
import { formatUniverseSpec } from "@/lib/eventStatsLabels";
import { patternLabel, type PatternNameFields } from "@/lib/patternLabels";

export const MAX_COMPARE_RUNS = 5;
export const MIN_COMPARE_RUNS = 2;

/** 对比页每任务固定色（最多 5） */
export const COMPARE_COLORS = ["#0b6e4f", "#1f6feb", "#c23b22", "#b8860b", "#6b5b95"] as const;

export const RETURN_SHORT: Record<string, string> = {
  return_1: "1日",
  return_3: "3日",
  return_5: "5日",
  return_10: "10日",
  return_20: "20日",
  return_60: "60日",
  return_horizon: "窗末",
};

export function parseCompareIds(raw: string | null): string[] {
  if (!raw) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const part of raw.split(",")) {
    const id = part.trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push(id);
    if (out.length >= MAX_COMPARE_RUNS) break;
  }
  return out;
}

export function compareIdsToSearch(ids: string[]): string {
  const cleaned = parseCompareIds(ids.join(","));
  return cleaned.length ? `ids=${cleaned.map(encodeURIComponent).join(",")}` : "";
}

/** 加入对比：保留已有 ids，追加当前，去重截断 */
export function mergeCompareIds(existing: string[], addId: string): string[] {
  return parseCompareIds([...existing, addId].join(","));
}

export function runCompareLabel(run: EventStatsRun, index: number): string {
  const short = run.run_id.slice(0, 8);
  return `T${index + 1}·${short}`;
}

export function runCompareTitle(
  run: EventStatsRun,
  patternMeta?: PatternNameFields | null,
): string {
  return `${patternLabel(run.entry_pattern_id, patternMeta)} · ${run.start_date}→${run.end_date}`;
}

export function runCompareSubtitle(run: EventStatsRun): string {
  const cov = (run.summary?.coverage || {}) as Record<string, unknown>;
  const events = cov.event_count ?? run.event_count ?? "—";
  const stocks = cov.stock_count ?? "—";
  return `${formatUniverseSpec(run.universe_spec)} · 窗 ${run.horizon_bars} 日 · ${events} 事件 / ${stocks} 股`;
}

export function compareColor(index: number): string {
  return COMPARE_COLORS[index % COMPARE_COLORS.length];
}

const COMPARE_IDS_STORAGE = "es-compare-ids";

export function loadStoredCompareIds(): string[] {
  try {
    return parseCompareIds(sessionStorage.getItem(COMPARE_IDS_STORAGE));
  } catch {
    return [];
  }
}

export function saveStoredCompareIds(ids: string[]): void {
  try {
    const cleaned = parseCompareIds(ids.join(","));
    if (cleaned.length) sessionStorage.setItem(COMPARE_IDS_STORAGE, cleaned.join(","));
    else sessionStorage.removeItem(COMPARE_IDS_STORAGE);
  } catch {
    /* ignore */
  }
}

/** 详情页「加入对比」：合并已选并返回目标 URL（调用方负责跳转） */
export function buildCompareHrefWithAdd(addId: string): string {
  const next = mergeCompareIds(loadStoredCompareIds(), addId);
  saveStoredCompareIds(next);
  return `/event-stats/compare?ids=${next.map(encodeURIComponent).join(",")}`;
}
