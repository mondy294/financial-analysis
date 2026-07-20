import { useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EarningsGuidance } from "@/api/client";
import { fmtPct } from "@/lib/eventStatsLabels";

export type FinancialHighlightPoint = {
  year: number;
  report_period: string;
  report_name?: string;
  /** 该期报告公告日（东财 NOTICE_DATE） */
  notice_date?: string | null;
  is_annual?: boolean;
  revenue?: number | null;
  revenue_yoy?: number | null;
  parent_net_profit?: number | null;
  parent_net_profit_yoy?: number | null;
  ded_net_profit?: number | null;
  ded_net_profit_yoy?: number | null;
  roe?: number | null;
  /** 报告公告日 PE(TTM) */
  pe_ttm?: number | null;
  pe_static?: number | null;
  valuation_date?: string | null;
  /** @deprecated 旧字段 */
  yoy?: number | null;
};

function fmtPe(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(1);
}

type MetricKey = "parent_net_profit" | "ded_net_profit" | "revenue";

const METRICS: { key: MetricKey; label: string; yoyKey: keyof FinancialHighlightPoint }[] = [
  { key: "parent_net_profit", label: "归母净利润", yoyKey: "parent_net_profit_yoy" },
  { key: "ded_net_profit", label: "扣非净利润", yoyKey: "ded_net_profit_yoy" },
  { key: "revenue", label: "营业总收入", yoyKey: "revenue_yoy" },
];

/** A 股：涨红跌绿 */
function yoyColor(v: number | null | undefined): string | undefined {
  if (v == null || Number.isNaN(v)) return undefined;
  if (v > 0) return "#c23b22";
  if (v < 0) return "#0b6e4f";
  return undefined;
}

function fmtYi(yuan: number | null | undefined): string {
  if (yuan == null || Number.isNaN(yuan)) return "—";
  const yi = yuan / 1e8;
  const abs = Math.abs(yi);
  if (abs >= 100) return `${yi.toFixed(1)} 亿`;
  if (abs >= 1) return `${yi.toFixed(2)} 亿`;
  if (abs >= 0.01) return `${yi.toFixed(3)} 亿`;
  return `${(yuan / 1e4).toFixed(0)} 万`;
}

function fmtYiRange(lo?: number | null, hi?: number | null, mid?: number | null): string {
  if (lo != null && hi != null) return `${fmtYi(lo)} ~ ${fmtYi(hi)}`;
  if (mid != null) return fmtYi(mid);
  if (lo != null) return fmtYi(lo);
  if (hi != null) return fmtYi(hi);
  return "—";
}

function fmtPctRange(lo?: number | null, hi?: number | null, mid?: number | null): string {
  if (lo != null && hi != null) return `${fmtPct(lo)} ~ ${fmtPct(hi)}`;
  if (mid != null) return fmtPct(mid);
  if (lo != null) return fmtPct(lo);
  if (hi != null) return fmtPct(hi);
  return "—";
}

function isMidyearPeriod(period: string | undefined): boolean {
  return !!period && /(?:-06-30|06\/30)/.test(period);
}

function guidanceKindLabel(g: EarningsGuidance): string {
  const mid = isMidyearPeriod(g.report_period);
  if (g.kind === "express") return mid ? "中报快报" : "业绩快报";
  return mid ? "中报预告" : "业绩预告";
}

/** 近五年中报预告/快报详细卡片（新→旧） */
function GuidanceDetailBlock({ items }: { items: EarningsGuidance[] }) {
  const detailItems = useMemo(() => {
    const kindRank = { forecast: 0, express: 1 } as Record<string, number>;
    const midyear = items.filter((g) => isMidyearPeriod(g.report_period));
    const pool = midyear.length ? midyear : items;
    return pool
      .slice()
      .sort((a, b) => {
        const pa = String(a.report_period || "");
        const pb = String(b.report_period || "");
        if (pa !== pb) return pb.localeCompare(pa);
        return (kindRank[String(a.kind)] ?? 9) - (kindRank[String(b.kind)] ?? 9);
      });
  }, [items]);

  if (!detailItems.length) return null;

  return (
    <div style={{ marginBottom: "0.85rem" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: "0.4rem",
          gap: "0.5rem",
          flexWrap: "wrap",
        }}
      >
        <strong style={{ fontSize: "0.9rem" }}>近五年中报预告 / 快报</strong>
        <span className="muted" style={{ fontSize: "0.78rem" }}>
          共 {detailItems.length} 条 · 含公告日、预测区间与变动原因
        </span>
      </div>
      {detailItems.map((g) => {
        const kindLabel = guidanceKindLabel(g);
        return (
          <div
            key={`${g.kind}-${g.report_period}`}
            style={{
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "0.65rem 0.75rem",
              marginBottom: "0.5rem",
              background: "color-mix(in srgb, #f59e0b 8%, transparent)",
            }}
          >
            <div
              style={{
                display: "flex",
                gap: "0.5rem",
                flexWrap: "wrap",
                alignItems: "baseline",
              }}
            >
              <strong>{g.report_name || kindLabel}</strong>
              <span className="badge">{kindLabel}</span>
              {g.notice_date ? (
                <span className="muted mono" style={{ fontSize: "0.78rem" }}>
                  预告公告 {g.notice_date}
                </span>
              ) : (
                <span className="muted" style={{ fontSize: "0.78rem" }}>
                  无公告日
                </span>
              )}
              <span className="muted mono" style={{ fontSize: "0.78rem" }}>
                报告期 {g.report_period}
              </span>
              {g.pe_ttm != null ? (
                <span className="mono" style={{ fontSize: "0.78rem" }}>
                  公告日 PE {fmtPe(g.pe_ttm)}
                  {g.valuation_date ? (
                    <span className="muted">（{g.valuation_date}）</span>
                  ) : null}
                </span>
              ) : null}
            </div>
            {g.kind === "express" ? (
              <dl className="kv" style={{ marginTop: "0.45rem" }}>
                <dt>营收</dt>
                <dd className="mono">{fmtYi(g.revenue)}</dd>
                <dt>营收同比</dt>
                <dd className="mono" style={{ color: yoyColor(g.revenue_yoy) }}>
                  {fmtPct(g.revenue_yoy)}
                </dd>
                <dt>归母净利</dt>
                <dd className="mono">{fmtYi(g.parent_net_profit)}</dd>
                <dt>归母同比</dt>
                <dd
                  className="mono"
                  style={{ color: yoyColor(g.parent_net_profit_yoy) }}
                >
                  {fmtPct(g.parent_net_profit_yoy)}
                </dd>
                <dt>ROE</dt>
                <dd className="mono">{fmtPct(g.roe)}</dd>
                <dt>公告日 PE</dt>
                <dd className="mono">{fmtPe(g.pe_ttm)}</dd>
              </dl>
            ) : (
              <div className="table-wrap" style={{ marginTop: "0.45rem" }}>
                <table className="data">
                  <thead>
                    <tr>
                      <th>指标</th>
                      <th>类型</th>
                      <th style={{ textAlign: "right" }}>预测区间</th>
                      <th style={{ textAlign: "right" }}>同比区间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(g.metrics || []).map((m) => (
                      <tr key={m.metric}>
                        <td>{m.metric}</td>
                        <td>{m.predict_type || "—"}</td>
                        <td className="mono" style={{ textAlign: "right" }}>
                          {fmtYiRange(m.value_lower, m.value_upper, m.value_mid)}
                        </td>
                        <td
                          className="mono"
                          style={{
                            textAlign: "right",
                            color: yoyColor(m.yoy_mid ?? m.yoy_lower ?? m.yoy_upper),
                          }}
                        >
                          {fmtPctRange(m.yoy_lower, m.yoy_upper, m.yoy_mid)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {(g.metrics || [])[0]?.content ? (
                  <p className="muted" style={{ margin: "0.4rem 0 0", fontSize: "0.78rem" }}>
                    {(g.metrics || [])[0]?.content}
                  </p>
                ) : null}
                {(g.metrics || [])[0]?.reason ? (
                  <p className="muted" style={{ margin: "0.25rem 0 0", fontSize: "0.78rem" }}>
                    变动原因：{(g.metrics || [])[0]?.reason}
                  </p>
                ) : null}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

type SeriesPoint = FinancialHighlightPoint & {
  /** 尚无正式中报时，用预告/快报顶上；正式披露后会被替换 */
  proxy?: boolean;
  proxy_kind?: "forecast" | "express" | string;
  /** 单季序列中的季度 1–4 */
  quarter?: 1 | 2 | 3 | 4;
  /** 由累计报表差分得到（二季报=中报−一季报，四季报=年报−三季报等） */
  derived?: boolean;
};

type CumKind = "q1" | "h1" | "q3" | "annual";

function cumKindOf(period: string, isAnnual?: boolean): CumKind | null {
  if (isAnnual || /(?:-12-31|12\/31)/.test(period)) return "annual";
  if (/(?:-03-31|03\/31)/.test(period)) return "q1";
  if (/(?:-06-30|06\/30)/.test(period)) return "h1";
  if (/(?:-09-30|09\/30)/.test(period)) return "q3";
  return null;
}

function subAmt(a?: number | null, b?: number | null): number | null {
  if (a == null || b == null || !Number.isFinite(a) || !Number.isFinite(b)) return null;
  return a - b;
}

function growthRatio(cur?: number | null, prev?: number | null): number | null {
  if (cur == null || prev == null || !Number.isFinite(cur) || !Number.isFinite(prev)) {
    return null;
  }
  if (prev === 0) return null;
  return (cur - prev) / Math.abs(prev);
}

function diffAmts(
  hi: FinancialHighlightPoint,
  lo: FinancialHighlightPoint,
): Pick<
  FinancialHighlightPoint,
  "revenue" | "parent_net_profit" | "ded_net_profit"
> {
  return {
    revenue: subAmt(hi.revenue, lo.revenue),
    parent_net_profit: subAmt(hi.parent_net_profit, lo.parent_net_profit),
    ded_net_profit: subAmt(hi.ded_net_profit, lo.ded_net_profit),
  };
}

/**
 * 累计报表 → 单季序列：
 * Q1=一季报；Q2=中报−一季报；Q3=三季报−中报；Q4=年报−三季报。
 * 并回填单季同比（相对去年同季）。
 */
function buildSingleQuarterSeries(cumul: SeriesPoint[]): SeriesPoint[] {
  const idx = new Map<string, SeriesPoint>();
  for (const p of cumul) {
    const period = String(p.report_period || "");
    const kind = cumKindOf(period, p.is_annual);
    if (!kind) continue;
    const year = p.year || Number(period.slice(0, 4));
    if (!Number.isFinite(year) || year <= 0) continue;
    const key = `${year}:${kind}`;
    const prev = idx.get(key);
    // 正式披露优先于预告占位
    if (!prev || (prev.proxy && !p.proxy)) idx.set(key, { ...p, year });
  }

  const years = [
    ...new Set(
      [...idx.keys()].map((k) => Number(k.split(":")[0])).filter((y) => Number.isFinite(y)),
    ),
  ].sort((a, b) => a - b);

  const out: SeriesPoint[] = [];
  for (const y of years) {
    const q1 = idx.get(`${y}:q1`);
    const h1 = idx.get(`${y}:h1`);
    const q3 = idx.get(`${y}:q3`);
    const ann = idx.get(`${y}:annual`);

    if (q1) {
      out.push({
        ...q1,
        year: y,
        report_period: `${y}-Q1`,
        report_name: `${y}一季报`,
        is_annual: false,
        quarter: 1,
        derived: false,
      });
    }

    if (h1 && q1) {
      const amts = diffAmts(h1, q1);
      if (
        amts.revenue != null ||
        amts.parent_net_profit != null ||
        amts.ded_net_profit != null
      ) {
        out.push({
          year: y,
          report_period: `${y}-Q2`,
          report_name: `${y}二季报`,
          notice_date: h1.notice_date,
          is_annual: false,
          ...amts,
          pe_ttm: h1.pe_ttm,
          pe_static: h1.pe_static,
          valuation_date: h1.valuation_date,
          quarter: 2,
          derived: true,
          proxy: h1.proxy,
          proxy_kind: h1.proxy_kind,
        });
      }
    }

    if (q3 && h1) {
      const amts = diffAmts(q3, h1);
      if (
        amts.revenue != null ||
        amts.parent_net_profit != null ||
        amts.ded_net_profit != null
      ) {
        out.push({
          year: y,
          report_period: `${y}-Q3`,
          report_name: `${y}三季报`,
          notice_date: q3.notice_date,
          is_annual: false,
          ...amts,
          pe_ttm: q3.pe_ttm,
          pe_static: q3.pe_static,
          valuation_date: q3.valuation_date,
          quarter: 3,
          derived: true,
          proxy: !!(q3.proxy || h1.proxy),
          proxy_kind: q3.proxy_kind || h1.proxy_kind,
        });
      }
    }

    if (ann && q3) {
      const amts = diffAmts(ann, q3);
      if (
        amts.revenue != null ||
        amts.parent_net_profit != null ||
        amts.ded_net_profit != null
      ) {
        out.push({
          year: y,
          report_period: `${y}-Q4`,
          report_name: `${y}四季报`,
          notice_date: ann.notice_date,
          is_annual: false,
          ...amts,
          pe_ttm: ann.pe_ttm,
          pe_static: ann.pe_static,
          valuation_date: ann.valuation_date,
          quarter: 4,
          derived: true,
        });
      }
    }
  }

  const byYQ = new Map(
    out
      .filter((p) => p.quarter != null)
      .map((p) => [`${p.year}Q${p.quarter}`, p] as const),
  );
  for (const p of out) {
    if (p.quarter == null) continue;
    const prev = byYQ.get(`${(p.year || 0) - 1}Q${p.quarter}`);
    p.revenue_yoy = growthRatio(p.revenue, prev?.revenue);
    p.parent_net_profit_yoy = growthRatio(
      p.parent_net_profit,
      prev?.parent_net_profit,
    );
    p.ded_net_profit_yoy = growthRatio(p.ded_net_profit, prev?.ded_net_profit);
  }

  return out.sort((a, b) => {
    const ya = a.year || 0;
    const yb = b.year || 0;
    if (ya !== yb) return ya - yb;
    return (a.quarter || 0) - (b.quarter || 0);
  });
}

function periodTypeLabel(p: SeriesPoint, forecastOnly: boolean): string | null {
  const period = String(p.report_period || "");
  if (forecastOnly) {
    return p.proxy_kind === "express" ? "中报快报" : "中报预告";
  }
  if (p.is_annual) return null;
  if (isMidyearPeriod(period)) return "中报";
  if (/(?:-03-31|03\/31)/.test(period)) return "一季报";
  if (/(?:-09-30|09\/30)/.test(period)) return "三季报";
  return "季报";
}

function periodLabel(p: FinancialHighlightPoint): string {
  if (p.report_name) return p.report_name;
  return p.is_annual === false ? p.report_period : String(p.year);
}

function yoyOf(p: FinancialHighlightPoint, key: keyof FinancialHighlightPoint): number | null {
  const v = p[key];
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (key === "parent_net_profit_yoy" && typeof p.yoy === "number") return p.yoy;
  return null;
}

function midNum(lo?: number | null, hi?: number | null, mid?: number | null): number | null {
  if (mid != null && Number.isFinite(mid)) return mid;
  if (lo != null && hi != null && Number.isFinite(lo) && Number.isFinite(hi)) {
    return (lo + hi) / 2;
  }
  if (lo != null && Number.isFinite(lo)) return lo;
  if (hi != null && Number.isFinite(hi)) return hi;
  return null;
}

function pickGuidanceMetric(g: EarningsGuidance, patterns: RegExp[]) {
  const metrics = g.metrics || [];
  for (const re of patterns) {
    const hit = metrics.find((m) => re.test(m.metric || ""));
    if (hit) return hit;
  }
  return undefined;
}

/** 中报预告/快报 → 图表可用点；正式中报存在时不会调用 */
function guidanceToSeriesPoint(g: EarningsGuidance): SeriesPoint {
  const period = String(g.report_period || "");
  const year = Number(period.slice(0, 4));
  const y = Number.isFinite(year) ? year : 0;
  const isExpress = g.kind === "express";
  const label = isExpress ? "中报快报" : "中报预告";

  if (isExpress) {
    return {
      year: y,
      report_period: period,
      report_name: g.report_name || `${y}${label}`,
      notice_date: g.notice_date,
      is_annual: false,
      revenue: g.revenue,
      revenue_yoy: g.revenue_yoy,
      parent_net_profit: g.parent_net_profit,
      parent_net_profit_yoy: g.parent_net_profit_yoy,
      roe: g.roe,
      pe_ttm: g.pe_ttm,
      pe_static: g.pe_static,
      valuation_date: g.valuation_date,
      proxy: true,
      proxy_kind: "express",
    };
  }

  const parentM = pickGuidanceMetric(g, [
    /归属于母公司所有者的净利润|归母净利润|归母/,
    /净利润/,
  ]);
  const dedM = pickGuidanceMetric(g, [/扣除非经常性损益|扣非/]);
  const revM = pickGuidanceMetric(g, [/营业总收入|营业收入|营收/]);

  return {
    year: y,
    report_period: period,
    report_name: g.report_name || `${y}${label}`,
    notice_date: g.notice_date,
    is_annual: false,
    parent_net_profit: midNum(parentM?.value_lower, parentM?.value_upper, parentM?.value_mid),
    parent_net_profit_yoy: midNum(parentM?.yoy_lower, parentM?.yoy_upper, parentM?.yoy_mid),
    ded_net_profit: midNum(dedM?.value_lower, dedM?.value_upper, dedM?.value_mid),
    ded_net_profit_yoy: midNum(dedM?.yoy_lower, dedM?.yoy_upper, dedM?.yoy_mid),
    revenue: midNum(revM?.value_lower, revM?.value_upper, revM?.value_mid),
    revenue_yoy: midNum(revM?.yoy_lower, revM?.yoy_upper, revM?.yoy_mid),
    pe_ttm: g.pe_ttm,
    pe_static: g.pe_static,
    valuation_date: g.valuation_date,
    proxy: true,
    proxy_kind: "forecast",
  };
}

export function ParentProfitChart({
  points,
  loading,
  note,
  guidance = [],
}: {
  points: FinancialHighlightPoint[];
  loading?: boolean;
  note?: string;
  guidance?: EarningsGuidance[];
}) {
  const [metric, setMetric] = useState<MetricKey>("ded_net_profit");
  const meta = METRICS.find((m) => m.key === metric)!;

  const forecastByPeriod = useMemo(() => {
    const map = new Map<string, EarningsGuidance>();
    for (const g of guidance) {
      if (g.kind !== "forecast" && g.kind !== "express") continue;
      const key = String(g.report_period || "");
      if (!key) continue;
      const prev = map.get(key);
      // 列表预告列优先保留预告
      if (!prev || (prev.kind !== "forecast" && g.kind === "forecast")) {
        map.set(key, g);
      }
    }
    return map;
  }, [guidance]);

  /** 累计口径：正式点 + 尚无正式中报的预告/快报 */
  const cumulPoints = useMemo(() => {
    const formalByPeriod = new Map(
      points.map((p) => [String(p.report_period), p] as const),
    );
    const proxyByPeriod = new Map<string, EarningsGuidance>();
    for (const g of guidance) {
      if (g.kind !== "forecast" && g.kind !== "express") continue;
      const period = String(g.report_period || "");
      if (!isMidyearPeriod(period) || formalByPeriod.has(period)) continue;
      const prev = proxyByPeriod.get(period);
      if (!prev || (prev.kind !== "express" && g.kind === "express")) {
        proxyByPeriod.set(period, g);
      }
    }
    return [
      ...points.map((p) => ({ ...p, proxy: false as const })),
      ...[...proxyByPeriod.values()].map(guidanceToSeriesPoint),
    ];
  }, [points, guidance]);

  /** 图表：单季序列（含推算 Q2/Q4）+ 环比/同比 */
  const seriesPoints = useMemo(
    () => buildSingleQuarterSeries(cumulPoints),
    [cumulPoints],
  );

  const option = useMemo(() => {
    const labels = seriesPoints.map((p) => {
      const base = p.report_name || `${p.year}Q${p.quarter}`;
      if (p.proxy) {
        return `${base}${p.proxy_kind === "express" ? "·快报" : "·预告"}`;
      }
      if (p.derived) return `${base}·推算`;
      return base;
    });
    const values = seriesPoints.map((p) => {
      const v = p[metric];
      return typeof v === "number" ? v / 1e8 : null;
    });
    const yoys = seriesPoints.map((p) => {
      const v = yoyOf(p, meta.yoyKey);
      return v == null ? null : v * 100;
    });
    const qoqs = seriesPoints.map((p, i) => {
      if (i === 0) return null;
      const prev = seriesPoints[i - 1];
      const curV = p[metric];
      const prevV = prev?.[metric];
      const g = growthRatio(
        typeof curV === "number" ? curV : null,
        typeof prevV === "number" ? prevV : null,
      );
      return g == null ? null : g * 100;
    });
    return {
      color: ["#c23b22", "#0d9488", "#2563eb"],
      tooltip: {
        trigger: "axis",
        formatter: (params: unknown) => {
          const arr = Array.isArray(params) ? params : [params];
          const idx =
            typeof (arr[0] as { dataIndex?: number })?.dataIndex === "number"
              ? (arr[0] as { dataIndex: number }).dataIndex
              : 0;
          const p = seriesPoints[idx];
          const hint = p?.proxy
            ? `（${p.proxy_kind === "express" ? "中报快报" : "中报预告"}推算单季）`
            : p?.derived
              ? "（由累计报表差分推算）"
              : "";
          const lines = [
            `<div><strong>${p?.report_name || periodLabel(p)}</strong> ${hint}</div>`,
            p?.notice_date
              ? `<div class="muted">相关公告 ${p.notice_date}</div>`
              : "",
            p?.pe_ttm != null
              ? `<div>相关公告日 PE(TTM): ${Number(p.pe_ttm).toFixed(1)}</div>`
              : "",
          ];
          for (const item of arr as Array<{
            marker?: string;
            seriesName?: string;
            value?: number | null;
          }>) {
            const v = item.value;
            const text =
              v == null || Number.isNaN(Number(v))
                ? "—"
                : item.seriesName?.includes("%")
                  ? `${Number(v).toFixed(2)}%`
                  : `${Number(v).toFixed(2)} 亿`;
            lines.push(`<div>${item.marker || ""}${item.seriesName}: ${text}</div>`);
          }
          return lines.filter(Boolean).join("");
        },
      },
      legend: { data: [`${meta.label}(亿)`, "环比(%)", "同比(%)"], top: 0 },
      grid: { left: 52, right: 48, top: 36, bottom: 48 },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { rotate: 32, fontSize: 10 },
      },
      yAxis: [
        {
          type: "value",
          name: "亿",
          splitLine: { lineStyle: { type: "dashed", opacity: 0.35 } },
        },
        { type: "value", name: "%", splitLine: { show: false } },
      ],
      series: [
        {
          name: `${meta.label}(亿)`,
          type: "bar",
          data: values.map((v, i) => {
            const p = seriesPoints[i];
            const proxy = !!p?.proxy;
            const derived = !!p?.derived;
            let color = "#c23b22";
            if (proxy) color = "#7c3aed";
            else if (derived && (p.quarter === 2 || p.quarter === 4)) color = "#0d9488";
            else if (derived) color = "#f59e0b";
            else if (p?.quarter === 1 || p?.quarter === 3) color = "#f59e0b";
            else if (v != null && v < 0) color = "#0b6e4f";
            return {
              value: v,
              itemStyle: {
                color,
                opacity: proxy ? 0.72 : derived ? 0.8 : 0.9,
                borderType: proxy || derived ? "dashed" : "solid",
                borderColor: proxy ? "#5b21b6" : derived ? "#0f766e" : undefined,
                borderWidth: proxy || derived ? 1 : 0,
              },
            };
          }),
          barMaxWidth: 28,
        },
        {
          name: "环比(%)",
          type: "line",
          yAxisIndex: 1,
          data: qoqs,
          smooth: false,
          symbolSize: 6,
          lineStyle: { width: 2, color: "#0d9488" },
          itemStyle: { color: "#0d9488" },
        },
        {
          name: "同比(%)",
          type: "line",
          yAxisIndex: 1,
          data: yoys,
          smooth: true,
          symbolSize: 6,
          lineStyle: { width: 2, color: "#2563eb", type: "dashed" },
          itemStyle: { color: "#2563eb" },
        },
      ],
    };
  }, [seriesPoints, metric, meta.label, meta.yoyKey]);

  /** 正式财报行 + 尚无正式中报时的预告占位行 */
  const rows = useMemo(() => {
    const byPeriod = new Map(
      points.map((p) => [String(p.report_period), p] as const),
    );
    const merged: FinancialHighlightPoint[] = [...points];
    for (const [period, g] of forecastByPeriod) {
      if (!isMidyearPeriod(period) || byPeriod.has(period)) continue;
      merged.push(guidanceToSeriesPoint(g));
    }
    return merged
      .slice()
      .sort((a, b) => String(b.report_period).localeCompare(String(a.report_period)));
  }, [points, forecastByPeriod]);

  if (loading) {
    return <p className="muted" style={{ margin: 0 }}>加载财务指标…</p>;
  }
  if (!points.length && !guidance.length) {
    return <p className="muted" style={{ margin: 0 }}>暂无财务数据</p>;
  }

  return (
    <div>
      <GuidanceDetailBlock items={guidance} />
      {seriesPoints.length ? (
        <>
          <div className="tabs" style={{ marginBottom: "0.5rem" }}>
            {METRICS.map((m) => (
              <button
                key={m.key}
                type="button"
                className={metric === m.key ? "active" : ""}
                onClick={() => setMetric(m.key)}
              >
                {m.label}
              </button>
            ))}
          </div>
          <ReactECharts option={option} style={{ height: 320 }} notMerge lazyUpdate />
          <p className="muted" style={{ margin: "0.25rem 0 0", fontSize: "0.75rem" }}>
            图表为单季口径：Q2=中报−一季报，Q3=三季报−中报，Q4=年报−三季报；青绿虚边为推算季，紫色为预告/快报参与推算。折线为环比与同比。
          </p>
        </>
      ) : null}
      {rows.length ? (
        <div className="table-wrap" style={{ marginTop: seriesPoints.length ? "0.35rem" : 0 }}>
          <table className="data">
            <thead>
              <tr>
                <th>报告期</th>
                <th>正式公告日</th>
                <th style={{ textAlign: "right" }} title="正式报告公告日当日或之前最近交易日 PE(TTM)">
                  公告日PE
                </th>
                <th>预告公告日</th>
                <th style={{ textAlign: "right" }} title="预告/快报公告日 PE(TTM)">
                  预告日PE
                </th>
                <th style={{ textAlign: "right" }}>预告归母同比</th>
                <th style={{ textAlign: "right" }}>营收</th>
                <th style={{ textAlign: "right" }}>营收同比</th>
                <th style={{ textAlign: "right" }}>归母净利</th>
                <th style={{ textAlign: "right" }}>归母同比</th>
                <th style={{ textAlign: "right" }}>扣非净利</th>
                <th style={{ textAlign: "right" }}>扣非同比</th>
                <th style={{ textAlign: "right" }}>ROE</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => {
                const g = forecastByPeriod.get(String(p.report_period));
                const parentMetric =
                  (g?.metrics || []).find((m) =>
                    /归属于母公司|归母/.test(m.metric || ""),
                  ) || (g?.metrics || [])[0];
                const forecastYoy =
                  g?.kind === "express"
                    ? g.parent_net_profit_yoy
                    : parentMetric?.yoy_mid ??
                      parentMetric?.yoy_lower ??
                      parentMetric?.yoy_upper ??
                      null;
                const forecastOnly = !!(p as SeriesPoint).proxy;
                const typeLabel = periodTypeLabel(p, forecastOnly);
                const formalPe = p.pe_ttm;
                const guidancePe = g?.pe_ttm;
                return (
                  <tr key={p.report_period}>
                    <td>
                      <span className="mono">{periodLabel(p)}</span>
                      {typeLabel ? (
                        <span className="muted" style={{ marginLeft: 4, fontSize: "0.75rem" }}>
                          {typeLabel}
                        </span>
                      ) : null}
                    </td>
                    <td className="mono muted">{p.notice_date || "—"}</td>
                    <td
                      className="mono"
                      style={{ textAlign: "right" }}
                      title={
                        p.valuation_date
                          ? `估值日 ${p.valuation_date}`
                          : undefined
                      }
                    >
                      {fmtPe(formalPe)}
                    </td>
                    <td className="mono muted">{g?.notice_date || "—"}</td>
                    <td
                      className="mono"
                      style={{ textAlign: "right" }}
                      title={
                        g?.valuation_date
                          ? `估值日 ${g.valuation_date}`
                          : undefined
                      }
                    >
                      {fmtPe(guidancePe)}
                    </td>
                    <td
                      className="mono"
                      style={{
                        textAlign: "right",
                        color: yoyColor(forecastYoy),
                      }}
                    >
                      {g?.kind === "forecast" && parentMetric
                        ? fmtPctRange(
                            parentMetric.yoy_lower,
                            parentMetric.yoy_upper,
                            parentMetric.yoy_mid,
                          )
                        : forecastYoy != null
                          ? fmtPct(forecastYoy)
                          : "—"}
                    </td>
                    <td className="mono" style={{ textAlign: "right" }}>
                      {fmtYi(p.revenue)}
                    </td>
                    <td
                      className="mono"
                      style={{ textAlign: "right", color: yoyColor(p.revenue_yoy) }}
                    >
                      {fmtPct(p.revenue_yoy)}
                    </td>
                    <td className="mono" style={{ textAlign: "right" }}>
                      {fmtYi(p.parent_net_profit)}
                    </td>
                    <td
                      className="mono"
                      style={{
                        textAlign: "right",
                        color: yoyColor(yoyOf(p, "parent_net_profit_yoy")),
                      }}
                    >
                      {fmtPct(yoyOf(p, "parent_net_profit_yoy"))}
                    </td>
                    <td className="mono" style={{ textAlign: "right" }}>
                      {fmtYi(p.ded_net_profit)}
                    </td>
                    <td
                      className="mono"
                      style={{ textAlign: "right", color: yoyColor(p.ded_net_profit_yoy) }}
                    >
                      {fmtPct(p.ded_net_profit_yoy)}
                    </td>
                    <td className="mono" style={{ textAlign: "right" }}>
                      {fmtPct(p.roe)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
      <p className="muted" style={{ margin: "0.45rem 0 0", fontSize: "0.78rem" }}>
        {note ||
          "下方表格为累计披露口径；上方图表已拆成单季并补全 Q2/Q4。"}
        {rows.length
          ? " 公告日PE / 预告日PE 取对应公告日（或之前最近交易日）的 PE(TTM)。缺一季报/中报/三季报时对应单季无法推算。"
          : ""}
      </p>
    </div>
  );
}
