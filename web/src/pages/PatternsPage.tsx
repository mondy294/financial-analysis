import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type PatternHit } from "@/api/client";
import { JobProgress } from "@/components/JobProgress";
import { fmtPct } from "@/lib/eventStatsLabels";

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100, 200] as const;
const DEFAULT_PATTERN = "RANGE_BREAKOUT";
const DEFAULT_PAGE_SIZE = 20;

function formatRanges(hit: PatternHit): string {
  const ranges = hit.chosen_window_ranges;
  if (!ranges) {
    return Object.entries(hit.chosen_windows)
      .map(([k, v]) => `${k}:${v}d`)
      .join(" · ");
  }
  return Object.entries(ranges)
    .map(([k, r]) => `${k} ${r.start}→${r.end}`)
    .join(" · ");
}

/** A 股惯例：涨红跌绿 */
function retColor(v: number | null | undefined): string | undefined {
  if (v == null || Number.isNaN(v)) return undefined;
  if (v > 0) return "#c23b22";
  if (v < 0) return "#0b6e4f";
  return undefined;
}

type SortKey = "score" | "return_1" | "return_3" | "return_5";
type SortDir = "asc" | "desc";

const SORT_KEYS: SortKey[] = ["score", "return_1", "return_3", "return_5"];
const SORT_LABEL: Record<SortKey, string> = {
  score: "相似度",
  return_1: "1日收益",
  return_3: "3日收益",
  return_5: "5日收益",
};

function parseSortKey(raw: string | null): SortKey {
  return SORT_KEYS.includes(raw as SortKey) ? (raw as SortKey) : "score";
}

function parseSortDir(raw: string | null): SortDir {
  return raw === "asc" ? "asc" : "desc";
}

function sortValue(hit: PatternHit, key: SortKey): number | null {
  if (key === "score") return hit.pattern_score;
  const v = hit[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function compareHits(a: PatternHit, b: PatternHit, key: SortKey, dir: SortDir): number {
  const av = sortValue(a, key);
  const bv = sortValue(b, key);
  // 缺数据沉底，不参与升降序抢位
  if (av == null && bv == null) return a.code.localeCompare(b.code);
  if (av == null) return 1;
  if (bv == null) return -1;
  const cmp = av - bv;
  if (cmp !== 0) return dir === "asc" ? cmp : -cmp;
  return a.code.localeCompare(b.code);
}

function SortTh({
  label,
  sortKey,
  activeKey,
  dir,
  align = "left",
  title,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  activeKey: SortKey;
  dir: SortDir;
  align?: "left" | "right";
  title?: string;
  onSort: (key: SortKey) => void;
}) {
  const active = activeKey === sortKey;
  const mark = active ? (dir === "desc" ? " ↓" : " ↑") : "";
  return (
    <th style={{ textAlign: align }} title={title}>
      <button
        type="button"
        className="sort-th"
        onClick={() => onSort(sortKey)}
        aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
      >
        {label}
        {mark}
      </button>
    </th>
  );
}

function RetCell({ v }: { v: number | null | undefined }) {
  return (
    <td className="mono" style={{ textAlign: "right", color: retColor(v) }}>
      {fmtPct(v)}
    </td>
  );
}

function summarizeReturns(rows: PatternHit[]) {
  const keys = ["return_1", "return_3", "return_5"] as const;
  const out: Record<
    (typeof keys)[number],
    { mean: number | null; win: number | null; n: number }
  > = {
    return_1: { mean: null, win: null, n: 0 },
    return_3: { mean: null, win: null, n: 0 },
    return_5: { mean: null, win: null, n: 0 },
  };
  for (const k of keys) {
    const vals = rows
      .map((r) => r[k])
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    if (!vals.length) continue;
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
    const win = vals.filter((v) => v > 0).length / vals.length;
    out[k] = { mean, win, n: vals.length };
  }
  return out;
}

function PageSizeSelect({
  value,
  onChange,
}: {
  value: number;
  onChange: (n: number) => void;
}) {
  return (
    <label className="pager-size">
      每页数量
      <select value={value} onChange={(e) => onChange(Number(e.target.value))}>
        {PAGE_SIZE_OPTIONS.map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>
    </label>
  );
}

function parsePageSize(raw: string | null): number {
  const n = Number(raw || DEFAULT_PAGE_SIZE);
  return (PAGE_SIZE_OPTIONS as readonly number[]).includes(n) ? n : DEFAULT_PAGE_SIZE;
}

export function PatternsPage() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ["trading-day"], queryFn: api.tradingDay });
  const patterns = useQuery({ queryKey: ["patterns-meta"], queryFn: api.patternsMeta });

  const patternId = params.get("pattern") || DEFAULT_PATTERN;
  /** 兼容旧 URL ?date=；新版用 start/end */
  const start =
    params.get("start") || params.get("date") || "";
  const end =
    params.get("end") || params.get("date") || start;
  const page = Math.max(1, Number(params.get("page") || "1") || 1);
  const pageSize = parsePageSize(params.get("pageSize"));
  const sortKey = parseSortKey(params.get("sort"));
  const sortDir = parseSortDir(params.get("dir"));
  const multiDay = !!start && !!end && start !== end;

  const [jobId, setJobId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const patchParams = (updates: Record<string, string | null>) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(updates)) {
          if (v == null || v === "") next.delete(k);
          else next.set(k, v);
        }
        return next;
      },
      { replace: true },
    );
  };

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      patchParams({ dir: sortDir === "desc" ? "asc" : "desc", page: null });
      return;
    }
    // 收益默认降序（先看涨得多的）；相似度同理
    patchParams({
      sort: key === "score" ? null : key,
      dir: null,
      page: null,
    });
  };

  useEffect(() => {
    if (start && end) return;
    const d = meta.data?.pattern_latest_date || meta.data?.latest_trading_day;
    if (d) {
      patchParams({
        start: start || d,
        end: end || d,
        date: null,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta.data, start, end]);

  // 无 query 时补上默认 pattern，便于分享/返回时 URL 完整
  useEffect(() => {
    if (!params.get("pattern")) {
      patchParams({ pattern: patternId });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const top = useQuery({
    queryKey: ["pattern-top", patternId, start, end, "all"],
    queryFn: () =>
      api.patternTop(patternId, undefined, 0, { start, end }),
    enabled: !!start && !!end && !!patternId,
  });

  const ranked = useMemo(() => {
    const rows = [...(top.data || [])];
    rows.sort((a, b) => compareHits(a, b, sortKey, sortDir));
    return rows;
  }, [top.data, sortKey, sortDir]);

  const fwdSummary = useMemo(() => summarizeReturns(ranked), [ranked]);

  const totalPages = Math.max(1, Math.ceil(ranked.length / pageSize) || 1);
  const safePage = Math.min(page, totalPages);
  const pageRows = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return ranked.slice(start, start + pageSize);
  }, [ranked, safePage, pageSize]);

  useEffect(() => {
    setExpanded(null);
  }, [patternId, start, end, pageSize, sortKey, sortDir]);

  useEffect(() => {
    if (page > totalPages) patchParams({ page: String(totalPages) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, totalPages]);

  const listReturnPath = useMemo(() => {
    const q = new URLSearchParams();
    q.set("pattern", patternId);
    if (start) q.set("start", start);
    if (end) q.set("end", end);
    if (safePage > 1) q.set("page", String(safePage));
    if (pageSize !== DEFAULT_PAGE_SIZE) q.set("pageSize", String(pageSize));
    if (sortKey !== "score") q.set("sort", sortKey);
    if (sortDir !== "desc") q.set("dir", sortDir);
    return `/patterns?${q.toString()}`;
  }, [patternId, start, end, safePage, pageSize, sortKey, sortDir]);

  const stockHref = (code: string, tradeDate: string, evalTab = false) => {
    const q = new URLSearchParams();
    q.set("date", tradeDate);
    q.set("pattern", patternId);
    if (evalTab) q.set("eval", "1");
    q.set("return", listReturnPath);
    return `/stocks/${code}?${q.toString()}`;
  };

  const scan = useMutation({
    mutationFn: (force: boolean) =>
      api.scanPatterns({
        start_date: start || undefined,
        end_date: end || undefined,
        pattern_ids: [patternId],
        force,
      }),
    onSuccess: (job) => setJobId(job.job_id),
  });

  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "PENDING" || s === "RUNNING" ? 600 : false;
    },
  });

  const scanRunning =
    scan.isPending ||
    job.data?.status === "PENDING" ||
    job.data?.status === "RUNNING";

  useEffect(() => {
    if (job.data?.status === "SUCCESS") {
      void qc.invalidateQueries({ queryKey: ["pattern-top"] });
      void qc.invalidateQueries({ queryKey: ["trading-day"] });
    }
  }, [job.data?.status, qc]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Pattern 工作台</h1>
          <p className="muted">
            榜单 / 统计 / 触发扫描
            {start && end ? (
              <>
                {" "}
                · {start}
                {multiDay ? ` → ${end}` : ""}
              </>
            ) : null}
          </p>
        </div>
        <div className="toolbar">
          <label>
            开始
            <input
              type="date"
              value={start}
              onChange={(e) => {
                const v = e.target.value;
                if (v && end && v > end) {
                  patchParams({ start: v, end: v, date: null, page: null });
                } else {
                  patchParams({ start: v || null, date: null, page: null });
                }
              }}
            />
          </label>
          <label>
            结束
            <input
              type="date"
              value={end}
              onChange={(e) => {
                const v = e.target.value;
                if (v && start && v < start) {
                  patchParams({ start: v, end: v, date: null, page: null });
                } else {
                  patchParams({ end: v || null, date: null, page: null });
                }
              }}
            />
          </label>
          <label>
            Pattern
            <select
              value={patternId}
              onChange={(e) => patchParams({ pattern: e.target.value, page: null })}
            >
              {(patterns.data || []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name_en
                    ? `${p.display_name} / ${p.display_name_en}`
                    : p.display_name}{" "}
                  ({p.id})
                </option>
              ))}
            </select>
          </label>
          <PageSizeSelect
            value={pageSize}
            onChange={(n) =>
              patchParams({
                pageSize: n === DEFAULT_PAGE_SIZE ? null : String(n),
                page: null,
              })
            }
          />
          <button
            className="btn primary"
            type="button"
            disabled={scanRunning || !start || !end}
            onClick={() => scan.mutate(false)}
            title={
              multiDay
                ? `扫描 ${start} → ${end} 区间内每个交易日`
                : "扫描所选交易日"
            }
          >
            {scanRunning ? "扫描中…" : multiDay ? "区间扫描" : "扫描"}
          </button>
          <button
            className="btn"
            type="button"
            disabled={scanRunning || !start || !end}
            onClick={() => scan.mutate(true)}
          >
            强制重扫
          </button>
        </div>
      </div>

      {(scan.error || job.data?.error) && !jobId && (
        <div className="error-box">
          {(scan.error as Error)?.message || job.data?.error}
        </div>
      )}
      <JobProgress jobId={jobId} job={job.data} title="扫描进度" />

      <div className="cards">
        <div className="card">
          <div className="label">全部命中</div>
          <div className="value mono">{ranked.length || "—"}</div>
        </div>
        <div className="card">
          <div className="label">1 日均收益 / 胜率</div>
          <div className="value mono" style={{ fontSize: "1.05rem", color: retColor(fwdSummary.return_1.mean) }}>
            {fmtPct(fwdSummary.return_1.mean)}
            <span className="muted" style={{ fontWeight: 400, marginLeft: "0.35rem" }}>
              · {fmtPct(fwdSummary.return_1.win)}
            </span>
          </div>
        </div>
        <div className="card">
          <div className="label">3 日均收益 / 胜率</div>
          <div className="value mono" style={{ fontSize: "1.05rem", color: retColor(fwdSummary.return_3.mean) }}>
            {fmtPct(fwdSummary.return_3.mean)}
            <span className="muted" style={{ fontWeight: 400, marginLeft: "0.35rem" }}>
              · {fmtPct(fwdSummary.return_3.win)}
            </span>
          </div>
        </div>
        <div className="card">
          <div className="label">5 日均收益 / 胜率</div>
          <div className="value mono" style={{ fontSize: "1.05rem", color: retColor(fwdSummary.return_5.mean) }}>
            {fmtPct(fwdSummary.return_5.mean)}
            <span className="muted" style={{ fontWeight: 400, marginLeft: "0.35rem" }}>
              · {fmtPct(fwdSummary.return_5.win)}
            </span>
          </div>
        </div>
      </div>
      <p className="muted" style={{ margin: "0 0 0.75rem", fontSize: "0.82rem" }}>
        命中后涨幅：相对<strong>信号日收盘</strong>的前复权收益（T+1 / T+3 / T+5）。用来快速看「形态命中后短期有没有兑现」；未来不足交易日显示 —。
        最终评分阈值 {patterns.data?.find((p) => p.id === patternId)?.threshold ?? "—"} · 版本{" "}
        {patterns.data?.find((p) => p.id === patternId)?.version ?? "—"}
      </p>

      <div className="panel">
        <div className="panel-head">
          <span>
            全部命中 · {patternId}
            {ranked.length ? (
              <span className="muted">
                {" "}
                · {ranked.length} 只 · {SORT_LABEL[sortKey]}
                {sortDir === "desc" ? "降序" : "升序"}
              </span>
            ) : null}
          </span>
          <div className="pager-inline">
            {top.isFetching ? <span className="muted">加载中…</span> : null}
          </div>
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>#</th>
                {multiDay ? <th>信号日</th> : null}
                <th>代码</th>
                <SortTh
                  label="相似度"
                  sortKey="score"
                  activeKey={sortKey}
                  dir={sortDir}
                  onSort={toggleSort}
                />
                <SortTh
                  label="1日"
                  sortKey="return_1"
                  activeKey={sortKey}
                  dir={sortDir}
                  align="right"
                  title="信号日后第 1 个交易日收盘 / 信号收盘 - 1；点击排序"
                  onSort={toggleSort}
                />
                <SortTh
                  label="3日"
                  sortKey="return_3"
                  activeKey={sortKey}
                  dir={sortDir}
                  align="right"
                  title="信号日后第 3 个交易日收盘 / 信号收盘 - 1；点击排序"
                  onSort={toggleSort}
                />
                <SortTh
                  label="5日"
                  sortKey="return_5"
                  activeKey={sortKey}
                  dir={sortDir}
                  align="right"
                  title="信号日后第 5 个交易日收盘 / 信号收盘 - 1；点击排序"
                  onSort={toggleSort}
                />
                <th>窗口</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((r, i) => {
                const rank = (safePage - 1) * pageSize + i + 1;
                const rowKey = `${r.trade_date}:${r.code}`;
                return (
                  <Fragment key={rowKey}>
                    <tr>
                      <td className="mono">{rank}</td>
                      {multiDay ? (
                        <td className="mono muted">{r.trade_date}</td>
                      ) : null}
                      <td>
                        <button
                          type="button"
                          className="btn"
                          style={{ padding: "0.15rem 0.4rem" }}
                          onClick={() =>
                            setExpanded(expanded === rowKey ? null : rowKey)
                          }
                        >
                          ▾
                        </button>{" "}
                        <Link to={stockHref(r.code, r.trade_date)}>
                          <span className="mono">{r.code}</span> {r.name}
                        </Link>
                      </td>
                      <td className="mono">{r.pattern_score.toFixed(2)}</td>
                      <RetCell v={r.return_1} />
                      <RetCell v={r.return_3} />
                      <RetCell v={r.return_5} />
                      <td className="muted" style={{ maxWidth: 360 }}>
                        {formatRanges(r)}
                      </td>
                      <td className="links-row">
                        <Link to={stockHref(r.code, r.trade_date, true)}>详情</Link>
                        <Link
                          to={`/patterns/eval?code=${r.code}&date=${r.trade_date}&pattern=${r.pattern_id}`}
                        >
                          eval
                        </Link>
                      </td>
                    </tr>
                    {expanded === rowKey && (
                      <tr>
                        <td colSpan={multiDay ? 9 : 8}>
                          <div className="grid-2">
                            <div>
                              <strong>Stage</strong>
                              <pre className="mono" style={{ margin: "0.3rem 0", fontSize: 12 }}>
                                {JSON.stringify(r.stage_similarity, null, 2)}
                              </pre>
                            </div>
                            <div>
                              <strong>Features</strong>
                              <pre className="mono" style={{ margin: "0.3rem 0", fontSize: 12 }}>
                                {JSON.stringify(r.feature_similarity, null, 2)}
                              </pre>
                            </div>
                          </div>
                          {r.reasons?.length > 0 && (
                            <ul className="reason-list">
                              {r.reasons.map((x) => (
                                <li key={x}>{x}</li>
                              ))}
                            </ul>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {!top.isFetching && !ranked.length && (
                <tr>
                  <td colSpan={8} className="muted">
                    无命中记录
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {ranked.length > 0 && (
          <div className="pager">
            <PageSizeSelect
              value={pageSize}
              onChange={(n) =>
                patchParams({
                  pageSize: n === DEFAULT_PAGE_SIZE ? null : String(n),
                  page: null,
                })
              }
            />
            <span className="chart-sep" />
            <button
              type="button"
              className="btn"
              disabled={safePage <= 1}
              onClick={() => patchParams({ page: null })}
            >
              首页
            </button>
            <button
              type="button"
              className="btn"
              disabled={safePage <= 1}
              onClick={() =>
                patchParams({ page: safePage <= 2 ? null : String(safePage - 1) })
              }
            >
              上一页
            </button>
            <span className="mono pager-info">
              {safePage} / {totalPages}
              <span className="muted">
                {" "}
                · {(safePage - 1) * pageSize + 1}–
                {Math.min(safePage * pageSize, ranked.length)} / {ranked.length}
              </span>
            </span>
            <button
              type="button"
              className="btn"
              disabled={safePage >= totalPages}
              onClick={() => patchParams({ page: String(safePage + 1) })}
            >
              下一页
            </button>
            <button
              type="button"
              className="btn"
              disabled={safePage >= totalPages}
              onClick={() => patchParams({ page: String(totalPages) })}
            >
              末页
            </button>
          </div>
        )}
      </div>
    </>
  );
}
