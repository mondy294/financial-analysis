/** 事件统计：指标中文名与展示辅助 */

export const RETURN_KEYS = [
  "return_1",
  "return_3",
  "return_5",
  "return_10",
  "return_20",
  "return_60",
  "return_horizon",
] as const;

export const PATH_KEYS = [
  "mfe",
  "mae",
  "max_drawdown",
  "volatility",
  "bull_ratio",
] as const;

export const TIME_KEYS = [
  "highest_day",
  "lowest_day",
  "time_to_mfe",
  "time_to_mae",
  "up_days",
  "continuous_up_days",
  "forward_bars_available",
] as const;

export const METRIC_LABELS: Record<string, string> = {
  return_1: "1 日收益",
  return_3: "3 日收益",
  return_5: "5 日收益",
  return_10: "10 日收益",
  return_20: "20 日收益",
  return_60: "60 日收益",
  return_horizon: "观测窗末日收益",
  mfe: "最大有利偏移 (MFE)",
  mae: "最大不利偏移 (MAE)",
  max_drawdown: "窗内最大回撤",
  volatility: "日收益波动率",
  bull_ratio: "阳线占比",
  highest_day: "最高价出现日序",
  lowest_day: "最低价出现日序",
  time_to_mfe: "到达 MFE 日序",
  time_to_mae: "到达 MAE 日序",
  up_days: "上涨天数",
  continuous_up_days: "最长连涨天数",
  forward_bars_available: "可用未来交易日数",
};

export const METRIC_HINTS: Record<string, string> = {
  return_1: "信号日收盘 → 其后第 1 个交易日收盘",
  return_3: "信号日收盘 → 其后第 3 个交易日收盘",
  return_5: "信号日收盘 → 其后第 5 个交易日收盘",
  return_10: "信号日收盘 → 其后第 10 个交易日收盘",
  return_20: "信号日收盘 → 其后第 20 个交易日收盘",
  return_60: "信号日收盘 → 其后第 60 个交易日收盘",
  return_horizon: "信号日收盘 → 观测窗最后一日收盘",
  mfe: "观测窗内相对信号收盘的最大上涨幅度",
  mae: "观测窗内相对信号收盘的最大下跌幅度（正数）",
  max_drawdown: "观测窗内收盘价从峰值到谷底的最大回撤（正数）",
  volatility: "观测窗内日收益的样本标准差",
  bull_ratio: "观测窗内收盘>开盘的阳线占比",
  highest_day: "窗内最高价出现在第几个交易日（1=T+1）",
  lowest_day: "窗内最低价出现在第几个交易日（1=T+1）",
  time_to_mfe: "MFE 出现的相对交易日序号",
  time_to_mae: "MAE 出现的相对交易日序号",
  up_days: "收盘高于前收（首日用开盘）的天数",
  continuous_up_days: "最长连续上涨天数",
  forward_bars_available: "信号日后实际能取到的 K 线根数",
};

export const STATUS_LABELS: Record<string, string> = {
  SUCCESS: "成功",
  FAILED: "失败",
  CANCELLED: "已取消",
  RUNNING: "运行中",
  PENDING: "排队中",
  ok: "完整",
  truncated: "截断（未来不足）",
  insufficient: "不足",
};

/** 宇宙配置简短中文 */
export function formatUniverseSpec(spec: Record<string, unknown> | null | undefined): string {
  if (!spec || typeof spec !== "object") return "—";
  const kind = String(spec.kind || "all");
  if (kind === "all") return "全市场";
  if (kind === "pool") return `池 ${String(spec.pool || "—")}`;
  if (kind === "codes") {
    const codes = Array.isArray(spec.codes) ? spec.codes.map(String) : [];
    if (!codes.length) return "自选（空）";
    if (codes.length <= 3) return `自选 ${codes.join(",")}`;
    return `自选 ${codes.length} 只（${codes.slice(0, 2).join(",")}…）`;
  }
  if (kind === "cluster_sample" || kind === "clusters_sample" || kind === "sample_clusters") {
    const n = Array.isArray(spec.codes) ? spec.codes.length : null;
    const target = spec.target_samples ?? spec.max_total ?? "?";
    const seed = spec.seed ?? "?";
    const profile = String(spec.profile || "pearson_w60");
    const meta = spec.sample_meta as Record<string, unknown> | undefined;
    const sampled = n ?? meta?.n_sampled;
    return `簇抽样 ${sampled ?? "?"} 只（目标 ${target}）· ${profile} · seed=${seed}`;
  }
  return kind;
}

/** Job.params 配置摘要（运行中任务） */
export function formatJobParams(params: Record<string, unknown> | null | undefined): string {
  if (!params) return "";
  const parts: string[] = [];
  if (params.pattern_id) parts.push(String(params.pattern_id));
  if (params.start && params.end) parts.push(`${params.start} → ${params.end}`);
  const uni = params.universe;
  if (uni && typeof uni === "object") {
    parts.push(formatUniverseSpec(uni as Record<string, unknown>));
  }
  if (typeof params.horizon_bars === "number") {
    parts.push(`观测窗 ${params.horizon_bars} 日`);
  }
  const conc: string[] = [];
  if (params.day_concurrency != null) conc.push(`日×${params.day_concurrency}`);
  if (params.match_concurrency != null) conc.push(`匹配×${params.match_concurrency}`);
  if (params.observe_concurrency != null) conc.push(`Obs×${params.observe_concurrency}`);
  if (conc.length) parts.push(conc.join(" "));
  return parts.join(" · ");
}

export type MetricStats = {
  mean?: number | null;
  median?: number | null;
  p10?: number | null;
  p90?: number | null;
  win_rate?: number | null;
  n_valid?: number;
};

export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}

export function isRatioMetric(key: string): boolean {
  return (
    key.startsWith("return_") ||
    key === "mfe" ||
    key === "mae" ||
    key === "max_drawdown" ||
    key === "volatility" ||
    key === "bull_ratio"
  );
}

export function formatMetricValue(key: string, v: number | null | undefined): string {
  if (isRatioMetric(key)) return fmtPct(v);
  return fmtNum(v, key.includes("day") || key === "up_days" || key === "continuous_up_days" || key === "forward_bars_available" ? 1 : 2);
}

export function statsOf(
  summary: Record<string, unknown> | null | undefined,
  key: string,
): MetricStats {
  const metrics = (summary?.metrics || {}) as Record<string, MetricStats>;
  return metrics[key] || {};
}

/** 详情页一句话结论 */
export function buildRunNarrative(summary: Record<string, unknown> | null | undefined): string {
  if (!summary) return "暂无聚合结果。";
  const coverage = (summary.coverage || {}) as Record<string, unknown>;
  const events = coverage.event_count ?? "—";
  const stocks = coverage.stock_count ?? "—";
  const r5 = statsOf(summary, "return_5");
  const r10 = statsOf(summary, "return_10");
  const parts = [
    `共 ${events} 次命中，覆盖 ${stocks} 只股票。`,
    `5 日均收益 ${fmtPct(r5.mean)}，中位数 ${fmtPct(r5.median)}，胜率 ${fmtPct(r5.win_rate)}；`,
    `10 日均收益 ${fmtPct(r10.mean)}，中位数 ${fmtPct(r10.median)}，胜率 ${fmtPct(r10.win_rate)}。`,
  ];
  if (r5.p10 != null && r5.p90 != null) {
    parts.push(`5 日 P10～P90 约 ${fmtPct(r5.p10)}～${fmtPct(r5.p90)}。`);
  }
  return parts.join("");
}
