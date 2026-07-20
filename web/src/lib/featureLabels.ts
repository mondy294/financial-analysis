import type { FeatureCatalogItem } from "@/api/client";

/** 与后端 FEATURE_LABELS_ZH 对齐的兜底（catalog 未加载时） */
const FALLBACK_ZH: Record<string, string> = {
  amplitude: "振幅",
  close_vs_window_high: "相对窗口高点",
  peak_day: "最高价位置",
  total_return: "区间涨跌幅",
  slope: "价格斜率",
  linearity: "走势直线度",
  volatility: "波动率",
  volume_shrink_ratio: "后半段缩量比",
  bull_ratio: "阳线占比",
  body_ratio: "实体占比",
  avg_volume: "平均成交量",
  gap_open: "跳空开盘",
  close_strength: "收盘强度",
  volume_up_ratio: "放量日占比",
  volume_acceleration: "量能首尾比",
  volume_last_vs_avg: "尾日量/均量",
  volume_climax_day: "天量位置",
  upper_shadow_ratio: "上影占比",
  lower_shadow_ratio: "下影占比",
  max_drawdown_in_window: "段内最大回撤",
  return_first: "首日涨跌幅",
  return_last: "尾日涨跌幅",
  return_acceleration: "涨幅加速度",
  up_day_ratio: "上涨日占比",
  consecutive_up_ratio: "连涨占比",
  consecutive_up_days: "连涨天数",
  stall_score: "滞涨分",
  consecutive_volume_up_ratio: "连续放量占比",
  return_slope_accel: "斜率加速度",
  close_accel_ratio: "涨幅加速比",
  down_day_ratio: "下跌日占比",
  consecutive_down_days: "连跌天数",
  consecutive_down_ratio: "连跌占比",
  breakout_distance: "突破前高距离",
  volume_vs_platform: "相对前段放量",
  close_vs_platform_mid: "相对前段中轴",
  break_hold_ratio: "站上前高占比",
  price_position: "一年价位",
  price_percentile: "收盘分位",
  close_vs_high: "相对历史高点",
};

/** 指标展示名：中文短名优先，否则描述，最后英文 name */
export function featureLabel(
  nameOrItem: string | FeatureCatalogItem | null | undefined,
  catalog?: FeatureCatalogItem[] | null,
): string {
  if (nameOrItem && typeof nameOrItem === "object") {
    const f = nameOrItem;
    return (f.label || FALLBACK_ZH[f.name] || f.description || f.name || "—").toString();
  }
  const name = (nameOrItem || "").toString();
  if (!name) return "—";
  const hit = (catalog || []).find((c) => c.name === name);
  if (hit?.label) return hit.label;
  if (FALLBACK_ZH[name]) return FALLBACK_ZH[name];
  if (hit?.description) return hit.description;
  return name;
}

export function featureOptionText(f: FeatureCatalogItem): string {
  return featureLabel(f);
}
