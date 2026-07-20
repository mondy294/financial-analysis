import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Pager } from "@/components/Pager";
import { fmtPct } from "@/lib/eventStatsLabels";

const CATEGORIES: { id: string; label: string }[] = [
  { id: "forecast", label: "业绩预告" },
  { id: "express", label: "业绩快报" },
  { id: "interim", label: "半年度报告" },
  { id: "annual", label: "年度报告" },
  { id: "q1", label: "一季报" },
  { id: "q3", label: "三季报" },
  { id: "other", label: "其他财务" },
];

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 20;

/** 东财业绩预告常见类型（排序靠前）；数据里出现的其它值会追加到末尾 */
const PREDICT_TYPE_ORDER = [
  "预增",
  "略增",
  "续盈",
  "扭亏",
  "预减",
  "略减",
  "首亏",
  "续亏",
  "增亏",
  "减亏",
  "不确定",
  "正式报告",
] as const;

type NoticeItem = {
  code: string;
  name: string;
  board?: string;
  board_label?: string;
  category: string;
  category_label: string;
  notice_type: string;
  title: string;
  notice_date: string;
  url?: string | null;
  parent_np_yoy?: number | null;
  parent_np_value?: number | null;
  predict_type?: string | null;
  report_period?: string | null;
  parent_np_sq?: number | null;
  parent_np_qoq?: number | null;
  parent_np_qoq_prev?: number | null;
  parent_np_qoq_delta?: number | null;
  return_1d?: number | null;
  return_5d?: number | null;
  return_10d?: number | null;
  return_since_notice?: number | null;
  /** 最新总市值，亿元 */
  market_cap?: number | null;
};

type StockGroup = {
  code: string;
  name: string;
  board_label: string;
  latest_date: string;
  categoryLabels: string[];
  notices: NoticeItem[];
  parentNpYoy: number | null;
  parentNpQoq: number | null;
  parentNpQoqPrev: number | null;
  parentNpQoqDelta: number | null;
  predictType: string | null;
  marketCap: number | null;
  return1d: number | null;
  return5d: number | null;
  return10d: number | null;
  returnSinceNotice: number | null;
  forecastNoticeDate: string | null;
};

type SortKey =
  | "date"
  | "parent_yoy"
  | "qoq"
  | "qoq_prev"
  | "qoq_delta"
  | "mcap"
  | "ret_1"
  | "ret_5"
  | "ret_10"
  | "since_notice";
type SortDir = "asc" | "desc";

const RETURN_SORT_KEYS: SortKey[] = ["ret_1", "ret_5", "ret_10", "since_notice"];
const QOQ_SORT_KEYS: SortKey[] = ["qoq", "qoq_prev", "qoq_delta"];

function parseYiBound(raw: string | null): number | null {
  if (raw == null || !String(raw).trim()) return null;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

function fmtMcapYi(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (v >= 1000) return `${v.toFixed(0)} 亿`;
  if (v >= 100) return `${v.toFixed(1)} 亿`;
  if (v >= 10) return `${v.toFixed(1)} 亿`;
  return `${v.toFixed(2)} 亿`;
}

function todayISO(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function shiftDaysISO(iso: string, delta: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + delta);
  const yy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

function isInterimForecast(r: NoticeItem): boolean {
  if (r.category !== "forecast") return false;
  const text = `${r.title} ${r.notice_type}`;
  return /半年度|中报|中期业绩|1-6月|1－6月|1—6月/.test(text);
}

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

function pickPrimaryNotice(notices: NoticeItem[]): NoticeItem | null {
  if (!notices.length) return null;
  const interimFc = notices.find(isInterimForecast);
  if (interimFc) return interimFc;
  const interimReport = notices.find((n) => n.category === "interim");
  if (interimReport) return interimReport;
  const withYoy = notices.find(
    (n) => typeof n.parent_np_yoy === "number" && Number.isFinite(n.parent_np_yoy),
  );
  return withYoy || notices[0];
}

function aggregateByStock(rows: NoticeItem[]): StockGroup[] {
  const map = new Map<string, StockGroup>();
  for (const r of rows) {
    let g = map.get(r.code);
    if (!g) {
      g = {
        code: r.code,
        name: r.name,
        board_label: r.board_label || "—",
        latest_date: r.notice_date,
        categoryLabels: [],
        notices: [],
        parentNpYoy: null,
        parentNpQoq: null,
        parentNpQoqPrev: null,
        parentNpQoqDelta: null,
        predictType: null,
        marketCap: null,
        return1d: null,
        return5d: null,
        return10d: null,
        returnSinceNotice: null,
        forecastNoticeDate: null,
      };
      map.set(r.code, g);
    }
    g.notices.push(r);
    if (r.notice_date > g.latest_date) g.latest_date = r.notice_date;
    if (!g.categoryLabels.includes(r.category_label)) {
      g.categoryLabels.push(r.category_label);
    }
    if (
      typeof r.market_cap === "number" &&
      Number.isFinite(r.market_cap) &&
      (g.marketCap == null || r.market_cap > g.marketCap)
    ) {
      g.marketCap = r.market_cap;
    }
  }
  const groups = [...map.values()];
  for (const g of groups) {
    g.notices.sort(
      (a, b) => b.notice_date.localeCompare(a.notice_date) || a.title.localeCompare(b.title),
    );
    const primary = pickPrimaryNotice(g.notices);
    g.parentNpYoy = primary?.parent_np_yoy ?? null;
    g.parentNpQoq = primary?.parent_np_qoq ?? null;
    g.parentNpQoqPrev = primary?.parent_np_qoq_prev ?? null;
    g.parentNpQoqDelta = primary?.parent_np_qoq_delta ?? null;
    g.predictType = primary?.predict_type || null;
    if (g.marketCap == null && primary?.market_cap != null) {
      g.marketCap = primary.market_cap;
    }
    g.return1d = primary?.return_1d ?? null;
    g.return5d = primary?.return_5d ?? null;
    g.return10d = primary?.return_10d ?? null;
    g.returnSinceNotice = primary?.return_since_notice ?? null;
    g.forecastNoticeDate = primary?.notice_date || null;
  }
  return groups;
}

function cmpNullableNum(
  av: number | null,
  bv: number | null,
  mul: number,
  tie: () => number,
): number {
  if (av == null && bv == null) return tie();
  if (av == null) return 1;
  if (bv == null) return -1;
  if (av !== bv) return (av - bv) * mul;
  return tie();
}

function sortGroups(groups: StockGroup[], key: SortKey, dir: SortDir): StockGroup[] {
  const mul = dir === "asc" ? 1 : -1;
  const rows = [...groups];
  const retVal = (g: StockGroup): number | null => {
    if (key === "ret_1") return g.return1d;
    if (key === "ret_5") return g.return5d;
    if (key === "ret_10") return g.return10d;
    if (key === "since_notice") return g.returnSinceNotice;
    return null;
  };
  const qoqVal = (g: StockGroup): number | null => {
    if (key === "qoq") return g.parentNpQoq;
    if (key === "qoq_prev") return g.parentNpQoqPrev;
    if (key === "qoq_delta") return g.parentNpQoqDelta;
    return null;
  };
  rows.sort((a, b) => {
    if (key === "parent_yoy") {
      return cmpNullableNum(a.parentNpYoy, b.parentNpYoy, mul, () =>
        a.code.localeCompare(b.code),
      );
    }
    if (key === "mcap") {
      return cmpNullableNum(a.marketCap, b.marketCap, mul, () => a.code.localeCompare(b.code));
    }
    if (QOQ_SORT_KEYS.includes(key)) {
      return cmpNullableNum(qoqVal(a), qoqVal(b), mul, () => a.code.localeCompare(b.code));
    }
    if (RETURN_SORT_KEYS.includes(key)) {
      return cmpNullableNum(retVal(a), retVal(b), mul, () => a.code.localeCompare(b.code));
    }
    const cmp = a.latest_date.localeCompare(b.latest_date);
    if (cmp !== 0) return cmp * mul;
    return a.code.localeCompare(b.code);
  });
  return rows;
}

export function DisclosuresPage() {
  const [params, setParams] = useSearchParams();
  const today = todayISO();
  const end = params.get("end") || params.get("date") || today;
  const start = params.get("start") || (params.get("date") ? end : shiftDaysISO(end, -6));
  const mainOnly = params.get("main") === "1";
  const interimForecastOnly = params.get("interim_fc") === "1";
  /** 只看正式半年度报告（非预告） */
  const interimOnly = params.get("interim") === "1";
  /** 公告后股价涨跌（默认关，避免扫 K 线拖慢） */
  const showReturns = params.get("returns") === "1";
  /** 预告类型多选；空 = 不限。URL: ptype=预增,扭亏 */
  const selectedPredictTypes = useMemo(() => {
    const raw = params.get("ptype");
    if (!raw) return new Set<string>();
    return new Set(raw.split(",").map((s) => s.trim()).filter(Boolean));
  }, [params]);
  /** 总市值区间（亿元）；URL: mcap_min / mcap_max */
  const mcapMin = parseYiBound(params.get("mcap_min"));
  const mcapMax = parseYiBound(params.get("mcap_max"));
  const mcapMinInput = params.get("mcap_min") ?? "";
  const mcapMaxInput = params.get("mcap_max") ?? "";
  const page = Math.max(1, Number(params.get("page") || "1") || 1);
  const pageSizeRaw = Number(params.get("pageSize") || DEFAULT_PAGE_SIZE);
  const pageSize = (PAGE_SIZE_OPTIONS as readonly number[]).includes(pageSizeRaw)
    ? pageSizeRaw
    : DEFAULT_PAGE_SIZE;
  const sortParam = params.get("sort");
  const sortKey: SortKey =
    sortParam === "parent_yoy" ||
    sortParam === "qoq" ||
    sortParam === "qoq_prev" ||
    sortParam === "qoq_delta" ||
    sortParam === "mcap" ||
    sortParam === "since_notice" ||
    sortParam === "ret_1" ||
    sortParam === "ret_5" ||
    sortParam === "ret_10" ||
    sortParam === "date"
      ? sortParam
      : interimForecastOnly || interimOnly
        ? "parent_yoy"
        : "date";
  const sortDir: SortDir = params.get("dir") === "asc" ? "asc" : "desc";
  // 未开启股价列时，忽略收益排序，避免空列误导
  const effectiveSortKey: SortKey =
    !showReturns && RETURN_SORT_KEYS.includes(sortKey) ? "date" : sortKey;

  const selected = useMemo(() => {
    if (interimForecastOnly) return new Set(["forecast"]);
    if (interimOnly) return new Set(["interim"]);
    const raw = params.get("cat");
    if (!raw) return new Set(CATEGORIES.map((c) => c.id).filter((id) => id !== "other"));
    return new Set(raw.split(",").filter(Boolean));
  }, [params, interimForecastOnly, interimOnly]);

  const [expanded, setExpanded] = useState<string | null>(null);

  const q = useQuery({
    queryKey: [
      "disclosures",
      start,
      end,
      mainOnly,
      "enrich-yjbb-fast",
      "with-mcap",
      showReturns ? "returns" : "no-returns",
      interimOnly ? "interim" : interimForecastOnly ? "forecast" : "all",
    ],
    queryFn: () =>
      api.disclosures({
        startDate: start,
        endDate: end,
        mainOnly,
        // 业绩指标 + 单季环比；公告后涨跌单独开关
        enrichForecast: true,
        enrichReturns: showReturns,
        category: interimOnly
          ? "interim"
          : interimForecastOnly
            ? "forecast"
            : undefined,
      }),
    staleTime: 5 * 60 * 1000,
    enabled: !!start && !!end,
  });

  const patch = (updates: Record<string, string | null>) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(updates)) {
          if (v == null || v === "") next.delete(k);
          else next.set(k, v);
        }
        if ("start" in updates || "end" in updates) next.delete("date");
        return next;
      },
      { replace: true },
    );
  };

  const toggleCat = (id: string) => {
    if (interimForecastOnly || interimOnly) return;
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    const allDefault = next.size === CATEGORIES.length - 1 && !next.has("other");
    patch({
      cat: allDefault || next.size === 0 ? null : [...next].join(","),
      page: null,
    });
  };

  const togglePredictType = (t: string) => {
    const next = new Set(selectedPredictTypes);
    if (next.has(t)) next.delete(t);
    else next.add(t);
    patch({
      ptype: next.size ? [...next].join(",") : null,
      page: null,
    });
  };

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      patch({ dir: sortDir === "desc" ? "asc" : "desc", page: null });
      return;
    }
    patch({
      sort: key === "date" && !interimForecastOnly && !interimOnly ? null : key,
      dir: key === "parent_yoy" ? "desc" : "desc",
      page: null,
    });
  };

  /** 类别/中报等筛完之后、预告类型之前，用于类型计数 */
  const categoryFilteredNotices = useMemo(() => {
    let rows = q.data?.items || [];
    if (interimForecastOnly) {
      rows = rows.filter(isInterimForecast);
    } else if (interimOnly) {
      rows = rows.filter((r) => r.category === "interim");
    } else if (selected.size) {
      rows = rows.filter((r) => selected.has(r.category));
    }
    return rows;
  }, [q.data?.items, selected, interimForecastOnly, interimOnly]);

  const predictTypeCounts = useMemo(() => {
    const map = new Map<string, number>();
    for (const r of categoryFilteredNotices) {
      const t = (r.predict_type || "").trim();
      if (!t) continue;
      map.set(t, (map.get(t) || 0) + 1);
    }
    return map;
  }, [categoryFilteredNotices]);

  const predictTypeOptions = useMemo(() => {
    const present = [...predictTypeCounts.keys()];
    const ordered = PREDICT_TYPE_ORDER.filter((t) => predictTypeCounts.has(t));
    const rest = present
      .filter((t) => !(PREDICT_TYPE_ORDER as readonly string[]).includes(t))
      .sort((a, b) => (predictTypeCounts.get(b) || 0) - (predictTypeCounts.get(a) || 0));
    return [...ordered, ...rest];
  }, [predictTypeCounts]);

  const filteredNotices = useMemo(() => {
    if (!selectedPredictTypes.size) return categoryFilteredNotices;
    return categoryFilteredNotices.filter(
      (r) => r.predict_type && selectedPredictTypes.has(r.predict_type),
    );
  }, [categoryFilteredNotices, selectedPredictTypes]);

  const groups = useMemo(() => {
    let aggregated = aggregateByStock(filteredNotices);
    if (mcapMin != null || mcapMax != null) {
      aggregated = aggregated.filter((g) => {
        const m = g.marketCap;
        if (m == null || !Number.isFinite(m)) return false;
        if (mcapMin != null && m < mcapMin) return false;
        if (mcapMax != null && m > mcapMax) return false;
        return true;
      });
    }
    return sortGroups(aggregated, effectiveSortKey, sortDir);
  }, [filteredNotices, effectiveSortKey, sortDir, mcapMin, mcapMax]);

  const counts = useMemo(() => {
    const rows = q.data?.items || [];
    const base = Object.fromEntries(CATEGORIES.map((c) => [c.id, 0])) as Record<string, number>;
    for (const r of rows) {
      if (r.category in base) base[r.category] += 1;
    }
    return base;
  }, [q.data?.items]);

  const interimForecastStockCount = useMemo(() => {
    const rows = (q.data?.items || []).filter(isInterimForecast);
    return new Set(rows.map((r) => r.code)).size;
  }, [q.data?.items]);

  const totalPages = Math.max(1, Math.ceil(groups.length / pageSize) || 1);
  const safePage = Math.min(page, totalPages);
  const pageGroups = useMemo(() => {
    const from = (safePage - 1) * pageSize;
    return groups.slice(from, from + pageSize);
  }, [groups, safePage, pageSize]);

  useEffect(() => {
    setExpanded(null);
  }, [
    start,
    end,
    mainOnly,
    interimForecastOnly,
    interimOnly,
    showReturns,
    selectedPredictTypes,
    mcapMin,
    mcapMax,
    pageSize,
    effectiveSortKey,
    sortDir,
  ]);

  useEffect(() => {
    if (page > totalPages) patch({ page: String(totalPages) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, totalPages]);

  const rangeLabel = start === end ? start : `${start} ~ ${end}`;
  const sortMark = (key: SortKey) =>
    effectiveSortKey === key ? (sortDir === "desc" ? " ↓" : " ↑") : "";
  const yoyHeader = interimForecastOnly ? "扣非同比" : "净利润同比";
  const tableColSpan = 13 + (showReturns ? 4 : 0);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>财务披露日历</h1>
          <p className="muted">
            按股票聚合。预告同比为扣非；正式报告用业绩报表净利润（含东财季度环比，快）。公告后股价默认关
          </p>
        </div>
        <div className="toolbar">
          <label>
            开始
            <input
              type="date"
              value={start}
              onChange={(e) => {
                const v = e.target.value || null;
                if (v && end && v > end) patch({ start: v, end: v, page: null });
                else patch({ start: v, page: null });
              }}
            />
          </label>
          <label>
            结束
            <input
              type="date"
              value={end}
              onChange={(e) => {
                const v = e.target.value || null;
                if (v && start && v < start) patch({ start: v, end: v, page: null });
                else patch({ end: v, page: null });
              }}
            />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <input
              type="checkbox"
              checked={mainOnly}
              onChange={(e) =>
                patch({ main: e.target.checked ? "1" : null, page: null })
              }
            />
            只看主板
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <input
              type="checkbox"
              checked={interimForecastOnly}
              onChange={(e) =>
                patch({
                  interim_fc: e.target.checked ? "1" : null,
                  interim: null,
                  sort: e.target.checked ? "parent_yoy" : null,
                  dir: e.target.checked ? "desc" : null,
                  page: null,
                })
              }
            />
            只看中报预告
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <input
              type="checkbox"
              checked={interimOnly}
              onChange={(e) =>
                patch({
                  interim: e.target.checked ? "1" : null,
                  interim_fc: null,
                  sort: e.target.checked ? "parent_yoy" : null,
                  dir: e.target.checked ? "desc" : null,
                  page: null,
                })
              }
            />
            只看半年报
          </label>
          <label
            style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}
            title="关闭则不算公告后涨跌，列表更快"
          >
            <input
              type="checkbox"
              checked={showReturns}
              onChange={(e) => {
                const on = e.target.checked;
                const updates: Record<string, string | null> = {
                  returns: on ? "1" : null,
                  page: null,
                };
                if (!on && RETURN_SORT_KEYS.includes(sortKey)) updates.sort = null;
                patch(updates);
              }}
            />
            公告后股价
          </label>
          <label title="最新总市值下限，单位亿元；无市值数据的股票会被排除">
            市值≥
            <input
              type="number"
              min={0}
              step={10}
              placeholder="亿"
              value={mcapMinInput}
              onChange={(e) => {
                const v = e.target.value.trim();
                patch({ mcap_min: v === "" ? null : v, page: null });
              }}
              style={{ width: "4.5rem" }}
            />
          </label>
          <label title="最新总市值上限，单位亿元；无市值数据的股票会被排除">
            市值≤
            <input
              type="number"
              min={0}
              step={10}
              placeholder="亿"
              value={mcapMaxInput}
              onChange={(e) => {
                const v = e.target.value.trim();
                patch({ mcap_max: v === "" ? null : v, page: null });
              }}
              style={{ width: "4.5rem" }}
            />
          </label>
          {mcapMin != null || mcapMax != null ? (
            <button
              type="button"
              className="btn"
              onClick={() => patch({ mcap_min: null, mcap_max: null, page: null })}
            >
              清除市值
            </button>
          ) : null}
          <button
            type="button"
            className="btn"
            onClick={() => patch({ start: today, end: today, date: null, page: null })}
          >
            今天
          </button>
          <button
            type="button"
            className="btn"
            onClick={() =>
              patch({ start: shiftDaysISO(today, -6), end: today, date: null, page: null })
            }
          >
            近7日
          </button>
          <Link
            className="btn"
            to={`/disclosures/analyze?start_date=${start}&end_date=${end}${
              mainOnly ? "" : "&main=0"
            }`}
          >
            因子分析
          </Link>
          <Link className="btn" to="/analysis/earnings-events">
            业绩分析
          </Link>
        </div>
      </div>

      <div className="cards" style={{ marginBottom: "0.75rem" }}>
        {CATEGORIES.map((c) => (
          <button
            key={c.id}
            type="button"
            className="card"
            onClick={() => toggleCat(c.id)}
            disabled={interimForecastOnly || interimOnly}
            style={{
              cursor: interimForecastOnly || interimOnly ? "default" : "pointer",
              textAlign: "left",
              opacity: selected.has(c.id) ? 1 : 0.45,
              outline: selected.has(c.id) ? "1px solid var(--accent, #0b6e4f)" : undefined,
            }}
          >
            <div className="label">{c.label}</div>
            <div className="value mono">{q.isLoading ? "—" : counts[c.id]}</div>
          </button>
        ))}
        <div className="card">
          <div className="label">
            {interimForecastOnly ? "中报预告股票" : interimOnly ? "半年报股票" : "股票数"}
          </div>
          <div className="value mono">{q.isFetching ? "…" : groups.length}</div>
        </div>
        {!interimForecastOnly && !interimOnly ? (
          <div className="card">
            <div className="label">中报预告股票</div>
            <div className="value mono">{q.isLoading ? "—" : interimForecastStockCount}</div>
          </div>
        ) : null}
      </div>

      {predictTypeOptions.length > 0 ? (
        <div
          className="toolbar"
          style={{
            marginBottom: "0.75rem",
            flexWrap: "wrap",
            gap: "0.4rem",
            alignItems: "center",
          }}
        >
          <span className="muted" style={{ marginRight: "0.25rem" }}>
            预告类型
          </span>
          {predictTypeOptions.map((t) => {
            const on = selectedPredictTypes.has(t);
            const dimmed = selectedPredictTypes.size > 0 && !on;
            return (
              <button
                key={t}
                type="button"
                className="btn"
                onClick={() => togglePredictType(t)}
                title={on ? `取消筛选「${t}」` : `只看「${t}」`}
                style={{
                  opacity: dimmed ? 0.45 : 1,
                  outline: on ? "1px solid var(--accent, #0b6e4f)" : undefined,
                  fontWeight: on ? 600 : undefined,
                }}
              >
                {t}
                <span className="muted mono" style={{ marginLeft: "0.35rem" }}>
                  {predictTypeCounts.get(t) || 0}
                </span>
              </button>
            );
          })}
          {selectedPredictTypes.size > 0 ? (
            <button
              type="button"
              className="btn"
              onClick={() => patch({ ptype: null, page: null })}
            >
              清除类型
            </button>
          ) : null}
        </div>
      ) : null}

      {q.error && (
        <div className="error-box">{(q.error as Error).message || "加载失败"}</div>
      )}

      <div className="panel">
        <div className="panel-head">
          <span>
            {rangeLabel} · 按股票聚合
            {mainOnly ? <span className="muted"> · 仅主板</span> : null}
            {interimForecastOnly ? <span className="muted"> · 仅中报预告</span> : null}
            {interimOnly ? <span className="muted"> · 仅半年报</span> : null}
            {selectedPredictTypes.size > 0 ? (
              <span className="muted"> · 类型 {[...selectedPredictTypes].join("/")}</span>
            ) : null}
            {mcapMin != null || mcapMax != null ? (
              <span className="muted">
                {" "}
                · 市值
                {mcapMin != null ? `≥${mcapMin}` : ""}
                {mcapMin != null && mcapMax != null ? "且" : ""}
                {mcapMax != null ? `≤${mcapMax}` : ""}
                亿
              </span>
            ) : null}
            {q.isFetching ? <span className="muted"> · 加载中…</span> : null}
          </span>
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th style={{ width: 36 }} />
                <th>
                  <button type="button" className="sort-th" onClick={() => toggleSort("date")}>
                    最新公告日{sortMark("date")}
                  </button>
                </th>
                <th>代码</th>
                <th>名称</th>
                <th>板块</th>
                <th style={{ textAlign: "right" }}>
                  <button
                    type="button"
                    className="sort-th"
                    onClick={() => toggleSort("parent_yoy")}
                    title="预告=扣非同比；正式报告=业绩报表净利润同比"
                  >
                    {yoyHeader}
                    {sortMark("parent_yoy")}
                  </button>
                </th>
                <th style={{ textAlign: "right" }}>
                  <button
                    type="button"
                    className="sort-th"
                    onClick={() => toggleSort("qoq")}
                    title="正式报告优先用东财「净利润-季度环比」；预告等用累计差分推算"
                  >
                    环比{sortMark("qoq")}
                  </button>
                </th>
                <th style={{ textAlign: "right" }}>
                  <button
                    type="button"
                    className="sort-th"
                    onClick={() => toggleSort("qoq_prev")}
                    title="上一季的单季环比"
                  >
                    上季环比{sortMark("qoq_prev")}
                  </button>
                </th>
                <th style={{ textAlign: "right" }}>
                  <button
                    type="button"
                    className="sort-th"
                    onClick={() => toggleSort("qoq_delta")}
                    title="环比变化 = 本季环比 − 上季环比（百分点差）"
                  >
                    环比Δ{sortMark("qoq_delta")}
                  </button>
                </th>
                <th style={{ textAlign: "right" }}>
                  <button
                    type="button"
                    className="sort-th"
                    onClick={() => toggleSort("mcap")}
                    title="最新总市值（亿元，日频估值表）"
                  >
                    市值{sortMark("mcap")}
                  </button>
                </th>
                {showReturns ? (
                  <>
                    <th style={{ textAlign: "right" }}>
                      <button
                        type="button"
                        className="sort-th"
                        onClick={() => toggleSort("ret_1")}
                        title="公告日收盘 → 其后第 1 个交易日；不足则用至今（前复权）"
                      >
                        1日{sortMark("ret_1")}
                      </button>
                    </th>
                    <th style={{ textAlign: "right" }}>
                      <button
                        type="button"
                        className="sort-th"
                        onClick={() => toggleSort("ret_5")}
                        title="公告日收盘 → 其后第 5 个交易日；不足则用至今（前复权）"
                      >
                        5日{sortMark("ret_5")}
                      </button>
                    </th>
                    <th style={{ textAlign: "right" }}>
                      <button
                        type="button"
                        className="sort-th"
                        onClick={() => toggleSort("ret_10")}
                        title="公告日收盘 → 其后第 10 个交易日；不足则用至今（前复权）"
                      >
                        10日{sortMark("ret_10")}
                      </button>
                    </th>
                    <th style={{ textAlign: "right" }}>
                      <button
                        type="button"
                        className="sort-th"
                        onClick={() => toggleSort("since_notice")}
                        title="公告日收盘 → 最新收盘（前复权）"
                      >
                        至今{sortMark("since_notice")}
                      </button>
                    </th>
                  </>
                ) : null}
                <th>{interimOnly ? "口径" : "预告类型"}</th>
                <th>披露类型</th>
                <th style={{ textAlign: "right" }}>公告数</th>
              </tr>
            </thead>
            <tbody>
              {pageGroups.map((g) => {
                const open = expanded === g.code;
                const retTitle = g.forecastNoticeDate
                  ? `自 ${g.forecastNoticeDate} 公告日收盘`
                  : undefined;
                return (
                  <Fragment key={g.code}>
                    <tr>
                      <td>
                        <button
                          type="button"
                          className="btn"
                          style={{ padding: "0.15rem 0.4rem" }}
                          onClick={() => setExpanded(open ? null : g.code)}
                        >
                          {open ? "▴" : "▾"}
                        </button>
                      </td>
                      <td className="mono">{g.latest_date}</td>
                      <td>
                        <Link to={`/stocks/${g.code}?date=${g.latest_date}`}>
                          <span className="mono">{g.code}</span>
                        </Link>
                      </td>
                      <td>{g.name}</td>
                      <td className="muted">{g.board_label}</td>
                      <td
                        className="mono"
                        style={{ textAlign: "right", color: yoyColor(g.parentNpYoy) }}
                      >
                        {fmtPct(g.parentNpYoy)}
                      </td>
                      <td
                        className="mono"
                        style={{ textAlign: "right", color: yoyColor(g.parentNpQoq) }}
                      >
                        {fmtPct(g.parentNpQoq)}
                      </td>
                      <td
                        className="mono"
                        style={{ textAlign: "right", color: yoyColor(g.parentNpQoqPrev) }}
                      >
                        {fmtPct(g.parentNpQoqPrev)}
                      </td>
                      <td
                        className="mono"
                        style={{ textAlign: "right", color: yoyColor(g.parentNpQoqDelta) }}
                        title="本季环比 − 上季环比"
                      >
                        {fmtPct(g.parentNpQoqDelta)}
                      </td>
                      <td className="mono" style={{ textAlign: "right" }}>
                        {fmtMcapYi(g.marketCap)}
                      </td>
                      {showReturns ? (
                        <>
                          <td
                            className="mono"
                            style={{ textAlign: "right", color: yoyColor(g.return1d) }}
                            title={retTitle}
                          >
                            {fmtPct(g.return1d)}
                          </td>
                          <td
                            className="mono"
                            style={{ textAlign: "right", color: yoyColor(g.return5d) }}
                            title={retTitle}
                          >
                            {fmtPct(g.return5d)}
                          </td>
                          <td
                            className="mono"
                            style={{ textAlign: "right", color: yoyColor(g.return10d) }}
                            title={retTitle}
                          >
                            {fmtPct(g.return10d)}
                          </td>
                          <td
                            className="mono"
                            style={{
                              textAlign: "right",
                              color: yoyColor(g.returnSinceNotice),
                            }}
                            title={retTitle}
                          >
                            {fmtPct(g.returnSinceNotice)}
                          </td>
                        </>
                      ) : null}
                      <td>{g.predictType || "—"}</td>
                      <td>
                        {g.categoryLabels.map((lab) => (
                          <span
                            key={lab}
                            className="badge"
                            style={{ marginRight: 4, fontSize: "0.75rem" }}
                          >
                            {lab}
                          </span>
                        ))}
                      </td>
                      <td className="mono" style={{ textAlign: "right" }}>
                        {g.notices.length}
                      </td>
                    </tr>
                    {open && (
                      <tr>
                        <td colSpan={tableColSpan}>
                          <div className="table-wrap">
                            <table className="data">
                              <thead>
                                <tr>
                                  <th>公告日</th>
                                  <th>类别</th>
                                  <th>类型</th>
                                  <th style={{ textAlign: "right" }}>{yoyHeader}</th>
                                  <th style={{ textAlign: "right" }}>环比</th>
                                  <th style={{ textAlign: "right" }}>上季环比</th>
                                  <th style={{ textAlign: "right" }}>环比Δ</th>
                                  {showReturns ? (
                                    <>
                                      <th style={{ textAlign: "right" }}>1日</th>
                                      <th style={{ textAlign: "right" }}>5日</th>
                                      <th style={{ textAlign: "right" }}>10日</th>
                                      <th style={{ textAlign: "right" }}>至今</th>
                                    </>
                                  ) : null}
                                  <th style={{ textAlign: "right" }}>净利/预测</th>
                                  <th style={{ textAlign: "right" }}>单季净利</th>
                                  <th>标题</th>
                                  <th>链接</th>
                                </tr>
                              </thead>
                              <tbody>
                                {g.notices.map((n) => (
                                  <tr key={`${n.notice_date}-${n.category}-${n.title}`}>
                                    <td className="mono">{n.notice_date}</td>
                                    <td>{n.category_label}</td>
                                    <td className="muted">{n.notice_type}</td>
                                    <td
                                      className="mono"
                                      style={{
                                        textAlign: "right",
                                        color: yoyColor(n.parent_np_yoy),
                                      }}
                                    >
                                      {fmtPct(n.parent_np_yoy)}
                                    </td>
                                    <td
                                      className="mono"
                                      style={{
                                        textAlign: "right",
                                        color: yoyColor(n.parent_np_qoq),
                                      }}
                                    >
                                      {fmtPct(n.parent_np_qoq)}
                                    </td>
                                    <td
                                      className="mono"
                                      style={{
                                        textAlign: "right",
                                        color: yoyColor(n.parent_np_qoq_prev),
                                      }}
                                    >
                                      {fmtPct(n.parent_np_qoq_prev)}
                                    </td>
                                    <td
                                      className="mono"
                                      style={{
                                        textAlign: "right",
                                        color: yoyColor(n.parent_np_qoq_delta),
                                      }}
                                    >
                                      {fmtPct(n.parent_np_qoq_delta)}
                                    </td>
                                    {showReturns ? (
                                      <>
                                        <td
                                          className="mono"
                                          style={{
                                            textAlign: "right",
                                            color: yoyColor(n.return_1d),
                                          }}
                                        >
                                          {fmtPct(n.return_1d)}
                                        </td>
                                        <td
                                          className="mono"
                                          style={{
                                            textAlign: "right",
                                            color: yoyColor(n.return_5d),
                                          }}
                                        >
                                          {fmtPct(n.return_5d)}
                                        </td>
                                        <td
                                          className="mono"
                                          style={{
                                            textAlign: "right",
                                            color: yoyColor(n.return_10d),
                                          }}
                                        >
                                          {fmtPct(n.return_10d)}
                                        </td>
                                        <td
                                          className="mono"
                                          style={{
                                            textAlign: "right",
                                            color: yoyColor(n.return_since_notice),
                                          }}
                                        >
                                          {fmtPct(n.return_since_notice)}
                                        </td>
                                      </>
                                    ) : null}
                                    <td className="mono" style={{ textAlign: "right" }}>
                                      {fmtYi(n.parent_np_value)}
                                    </td>
                                    <td className="mono" style={{ textAlign: "right" }}>
                                      {fmtYi(n.parent_np_sq)}
                                    </td>
                                    <td style={{ maxWidth: 360 }}>{n.title}</td>
                                    <td>
                                      {n.url ? (
                                        <a href={n.url} target="_blank" rel="noreferrer">
                                          原文
                                        </a>
                                      ) : (
                                        "—"
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {!q.isFetching && !groups.length && (
                <tr>
                  <td colSpan={tableColSpan} className="muted">
                    {interimForecastOnly
                      ? "该区间无中报业绩预告（可放宽日期或取消「只看主板」）"
                      : interimOnly
                        ? "该区间无正式半年报公告（可放宽日期或取消「只看主板」）"
                        : "该区间无匹配披露（可放宽筛选）"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {groups.length > 0 && (
          <Pager
            page={safePage}
            pageSize={pageSize}
            total={groups.length}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            onPageChange={(p) => patch({ page: p <= 1 ? null : String(p) })}
            onPageSizeChange={(n) =>
              patch({
                pageSize: n === DEFAULT_PAGE_SIZE ? null : String(n),
                page: null,
              })
            }
          />
        )}
        <p className="muted" style={{ margin: "0.5rem 1rem 0.75rem", fontSize: "0.78rem" }}>
          预告：扣非同比（YJYG）。正式报告：业绩报表净利润同比 + 东财自带季度环比（全市场一张表，已缓存）。
          环比Δ=本季环比−上季环比。
          {showReturns
            ? " 已开「公告后股价」。"
            : " 「公告后股价」默认关。"}
        </p>
      </div>
    </>
  );
}
