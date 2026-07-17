import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type PatternHit } from "@/api/client";

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100, 200] as const;

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

export function PatternsPage() {
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ["trading-day"], queryFn: api.tradingDay });
  const patterns = useQuery({ queryKey: ["patterns-meta"], queryFn: api.patternsMeta });
  const [patternId, setPatternId] = useState("RANGE_BREAKOUT");
  const [date, setDate] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  useEffect(() => {
    if (!date && meta.data?.pattern_latest_date) {
      setDate(meta.data.pattern_latest_date);
    } else if (!date && meta.data?.latest_trading_day) {
      setDate(meta.data.latest_trading_day);
    }
  }, [meta.data, date]);

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
    setPage(1);
    setExpanded(null);
  }, [patternId, date, pageSize]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

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
      return s === "PENDING" || s === "RUNNING" ? 1500 : false;
    },
  });

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
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label>
            Pattern
            <select value={patternId} onChange={(e) => setPatternId(e.target.value)}>
              {(patterns.data || [{ id: "RANGE_BREAKOUT", display_name: "RANGE_BREAKOUT" }]).map(
                (p) => (
                  <option key={p.id} value={p.id}>
                    {p.display_name} ({p.id})
                  </option>
                ),
              )}
            </select>
          </label>
          <PageSizeSelect value={pageSize} onChange={setPageSize} />
          <button
            className="btn primary"
            type="button"
            disabled={scan.isPending}
            onClick={() => scan.mutate(false)}
          >
            扫描
          </button>
          <button
            className="btn"
            type="button"
            disabled={scan.isPending}
            onClick={() => scan.mutate(true)}
          >
            强制重扫
          </button>
        </div>
      </div>

      {(scan.error || job.data?.error) && (
        <div className="error-box">
          {(scan.error as Error)?.message || job.data?.error}
        </div>
      )}
      {jobId && (
        <div className="card" style={{ marginBottom: "1rem" }}>
          <div className="label">任务 {jobId}</div>
          <div>
            <span
              className={`badge ${
                job.data?.status === "SUCCESS"
                  ? "ok"
                  : job.data?.status === "FAILED"
                    ? "fail"
                    : "warn"
              }`}
            >
              {job.data?.status || "…"}
            </span>{" "}
            <span className="muted">{job.data?.message}</span>
          </div>
        </div>
      )}

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
                        <Link to={`/stocks/${r.code}?date=${r.trade_date}`}>
                          <span className="mono">{r.code}</span> {r.name}
                        </Link>
                      </td>
                      <td className="mono">{r.pattern_score.toFixed(2)}</td>
                      <td className="muted" style={{ maxWidth: 360 }}>
                        {formatRanges(r)}
                      </td>
                      <td className="links-row">
                        <Link to={`/stocks/${r.code}?date=${r.trade_date}&eval=1`}>详情</Link>
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
            <PageSizeSelect value={pageSize} onChange={setPageSize} />
            <span className="chart-sep" />
            <button
              type="button"
              className="btn"
              disabled={safePage <= 1}
              onClick={() => setPage(1)}
            >
              首页
            </button>
            <button
              type="button"
              className="btn"
              disabled={safePage <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
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
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              下一页
            </button>
            <button
              type="button"
              className="btn"
              disabled={safePage >= totalPages}
              onClick={() => setPage(totalPages)}
            >
              末页
            </button>
          </div>
        )}
      </div>
    </>
  );
}
