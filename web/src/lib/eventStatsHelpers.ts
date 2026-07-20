import type { EventStatsRun, Job } from "@/api/client";

export const ALL_START = "2010-01-01";
export type RangePreset = "1y" | "3y" | "5y" | "all" | "custom";
export type UniverseMode = "all" | "codes" | "cluster" | "cluster_sample";

export const RANGE_PRESETS: { id: RangePreset; label: string }[] = [
  { id: "1y", label: "近1年" },
  { id: "3y", label: "近3年" },
  { id: "5y", label: "近5年" },
  { id: "all", label: "全部" },
  { id: "custom", label: "自定义" },
];

export const CLUSTER_PROFILES = [
  { id: "pearson_w60", label: "收益相关 · W60" },
  { id: "pearson_w250", label: "收益相关 · W250" },
];

export const PAGE_SIZE_OPTIONS = [10, 20, 50] as const;

export function parseYmd(s: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const d = new Date(`${s}T00:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatYmd(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function shiftYears(endYmd: string, years: number): string {
  const end = parseYmd(endYmd);
  if (!end) return "";
  const start = new Date(end);
  start.setFullYear(start.getFullYear() - years);
  return formatYmd(start);
}

export function detectPreset(start: string, end: string, asOf: string): RangePreset {
  if (!start || !end || !asOf) return "custom";
  if (end !== asOf) return "custom";
  if (start === ALL_START) return "all";
  if (start === shiftYears(asOf, 1)) return "1y";
  if (start === shiftYears(asOf, 3)) return "3y";
  if (start === shiftYears(asOf, 5)) return "5y";
  return "custom";
}

export function runToProgressJob(r: EventStatsRun): Job {
  return {
    job_id: r.job_id || r.run_id,
    kind: "pattern.event_stats",
    status: r.status,
    created_at: r.created_at || new Date().toISOString(),
    progress: typeof r.progress === "number" ? r.progress : 0,
    message:
      r.progress_msg ||
      (r.job_alive === false
        ? "后台进程已丢失（可能服务重启），进度已冻结"
        : "运行中…"),
    error: r.error_msg,
    params: {
      pattern_id: r.entry_pattern_id,
      start: r.start_date,
      end: r.end_date,
      universe: r.universe_spec,
      horizon_bars: r.horizon_bars,
      run_id: r.run_id,
    },
    result: { run_id: r.run_id },
    cancel_requested: false,
  };
}

export function buildRerunBody(
  r: EventStatsRun,
  concurrency: { day: number; match: number; observe: number },
) {
  const uni = { ...(r.universe_spec || {}) } as Record<string, unknown>;
  const kind = String(uni.kind || "all");
  if (kind === "cluster_sample" || kind === "clusters_sample" || kind === "sample_clusters") {
    delete uni.codes;
    delete uni.sample_meta;
    delete uni.per_cluster; // 重跑时再由算法决定每簇深度
    uni.kind = "cluster_sample";
    if (!uni.profile && uni.profile_id) uni.profile = uni.profile_id;
    if (uni.target_samples == null && uni.max_total != null) {
      uni.target_samples = uni.max_total;
    }
  }
  return {
    pattern_id: r.entry_pattern_id,
    start: r.start_date,
    end: r.end_date,
    universe: uni as {
      kind: string;
      codes?: string[];
      pool?: string;
      profile?: string;
      target_samples?: number;
      max_total?: number;
      seed?: number;
      prefer?: string;
    },
    horizon_bars: r.horizon_bars,
    return_horizons: r.return_horizons,
    dedup_policy: r.dedup_policy || "cooldown_h",
    calendar: r.calendar,
    day_concurrency: concurrency.day,
    match_concurrency: concurrency.match,
    observe_concurrency: concurrency.observe,
  };
}

export function formatCreatedAt(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16).replace("T", " ");
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
