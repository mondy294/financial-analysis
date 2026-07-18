import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type PatternHit } from "@/api/client";
import { JobProgress } from "@/components/JobProgress";

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
  const date = params.get("date") || "";
  const page = Math.max(1, Number(params.get("page") || "1") || 1);
  const pageSize = parsePageSize(params.get("pageSize"));

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

  useEffect(() => {
    if (date) return;
    const d = meta.data?.pattern_latest_date || meta.data?.latest_trading_day;
    if (d) patchParams({ date: d });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta.data, date]);

  // 无 query 时补上默认 pattern，便于分享/返回时 URL 完整
  useEffect(() => {
    if (!params.get("pattern")) {
      patchParams({ pattern: patternId });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stats = useQuery({
    queryKey: ["pattern-stats", date],
    queryFn: () => api.patternStats(date || undefined),
    enabled: !!date,
  });
  const top = useQuery({
    queryKey: ["pattern-top", patternId, date, "all"],
    queryFn: () => api.patternTop(patternId, date || undefined, 0),
    enabled: !!date && !!patternId,
  });

  const ranked = useMemo(() => {
    const rows = [...(top.data || [])];
    rows.sort((a, b) => b.pattern_score - a.pattern_score || a.code.localeCompare(b.code));
    return rows;
  }, [top.data]);

  const totalPages = Math.max(1, Math.ceil(ranked.length / pageSize) || 1);
  const safePage = Math.min(page, totalPages);
  const pageRows = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return ranked.slice(start, start + pageSize);
  }, [ranked, safePage, pageSize]);

  useEffect(() => {
    setExpanded(null);
  }, [patternId, date, pageSize]);

  useEffect(() => {
    if (page > totalPages) patchParams({ page: String(totalPages) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, totalPages]);

  const listReturnPath = useMemo(() => {
    const q = new URLSearchParams();
    q.set("pattern", patternId);
    if (date) q.set("date", date);
    if (safePage > 1) q.set("page", String(safePage));
    if (pageSize !== DEFAULT_PAGE_SIZE) q.set("pageSize", String(pageSize));
    return `/patterns?${q.toString()}`;
  }, [patternId, date, safePage, pageSize]);

  const stockHref = (code: string, tradeDate: string, evalTab = false) => {
    const q = new URLSearchParams();
    q.set("date", tradeDate);
    if (evalTab) q.set("eval", "1");
    q.set("return", listReturnPath);
    return `/stocks/${code}?${q.toString()}`;
  };

  const scan = useMutation({
    mutationFn: (force: boolean) =>
      api.scanPatterns({
        trade_date: date || undefined,
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
      void qc.invalidateQueries({ queryKey: ["pattern-stats"] });
      void qc.invalidateQueries({ queryKey: ["trading-day"] });
    }
  }, [job.data?.status, qc]);

  const patternStat = stats.data?.stats?.[patternId];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Pattern 工作台</h1>
          <p className="muted">榜单 / 统计 / 触发扫描（Definition 仍在代码中维护）</p>
        </div>
        <div className="toolbar">
          <label>
            交易日
            <input
              type="date"
              value={date}
              onChange={(e) => patchParams({ date: e.target.value, page: null })}
            />
          </label>
          <label>
            Pattern
            <select
              value={patternId}
              onChange={(e) => patchParams({ pattern: e.target.value, page: null })}
            >
              {(patterns.data || [{ id: DEFAULT_PATTERN, display_name: DEFAULT_PATTERN }]).map(
                (p) => (
                  <option key={p.id} value={p.id}>
                    {p.display_name} ({p.id})
                  </option>
                ),
              )}
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
            disabled={scanRunning}
            onClick={() => scan.mutate(false)}
          >
            {scanRunning ? "扫描中…" : "扫描"}
          </button>
          <button
            className="btn"
            type="button"
            disabled={scanRunning}
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
          <div className="label">库内统计</div>
          <div className="value mono">
            {patternStat
              ? Object.values(patternStat).reduce((a, b) => a + b, 0)
              : "—"}
          </div>
        </div>
        <div className="card">
          <div className="label">阈值</div>
          <div className="value mono">
            {patterns.data?.find((p) => p.id === patternId)?.threshold ?? "—"}
          </div>
        </div>
        <div className="card">
          <div className="label">版本</div>
          <div className="value mono">
            {patterns.data?.find((p) => p.id === patternId)?.version ?? "—"}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <span>
            全部命中 · {patternId}
            {ranked.length ? (
              <span className="muted"> · {ranked.length} 只 · 相似度降序</span>
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
                <th>代码</th>
                <th>相似度</th>
                <th>窗口</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((r, i) => {
                const rank = (safePage - 1) * pageSize + i + 1;
                return (
                  <Fragment key={r.code}>
                    <tr>
                      <td className="mono">{rank}</td>
                      <td>
                        <button
                          type="button"
                          className="btn"
                          style={{ padding: "0.15rem 0.4rem" }}
                          onClick={() => setExpanded(expanded === r.code ? null : r.code)}
                        >
                          ▾
                        </button>{" "}
                        <Link to={stockHref(r.code, r.trade_date)}>
                          <span className="mono">{r.code}</span> {r.name}
                        </Link>
                      </td>
                      <td className="mono">{r.pattern_score.toFixed(2)}</td>
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
                    {expanded === r.code && (
                      <tr>
                        <td colSpan={5}>
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
                  <td colSpan={5} className="muted">
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
