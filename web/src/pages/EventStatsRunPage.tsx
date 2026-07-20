import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { JobProgress } from "@/components/JobProgress";
import { Pager } from "@/components/Pager";
import { RunDetailCharts } from "@/components/eventstats/RunDetailCharts";
import {
  METRIC_HINTS,
  METRIC_LABELS,
  PATH_KEYS,
  RETURN_KEYS,
  STATUS_LABELS,
  TIME_KEYS,
  buildRunNarrative,
  formatJobParams,
  formatMetricValue,
  formatUniverseSpec,
  fmtPct,
  statsOf,
} from "@/lib/eventStatsLabels";
import { buildCompareHrefWithAdd } from "@/lib/eventStatsCompare";
import { buildRerunBody, runToProgressJob } from "@/lib/eventStatsHelpers";
import { patternLabel } from "@/lib/patternLabels";

function StatsTable({
  title,
  keys,
  summary,
  showWinRate,
}: {
  title: string;
  keys: readonly string[];
  summary: Record<string, unknown>;
  showWinRate?: boolean;
}) {
  return (
    <div style={{ marginBottom: "0.75rem" }}>
      <div className="panel-head" style={{ border: "none", padding: "0.5rem 1rem" }}>
        {title}
      </div>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>指标</th>
              <th>含义</th>
              <th style={{ textAlign: "right" }}>均值</th>
              <th style={{ textAlign: "right" }}>中位数</th>
              <th style={{ textAlign: "right" }} title="偏悲观一侧（第 10% 分位）">
                P10
              </th>
              <th style={{ textAlign: "right" }} title="偏乐观一侧（第 90% 分位）">
                P90
              </th>
              {showWinRate ? <th style={{ textAlign: "right" }}>胜率</th> : null}
              <th style={{ textAlign: "right" }}>样本</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => {
              const s = statsOf(summary, key);
              return (
                <tr key={key}>
                  <td>{METRIC_LABELS[key] || key}</td>
                  <td className="muted" style={{ fontSize: "0.78rem", maxWidth: 260 }}>
                    {METRIC_HINTS[key] || "—"}
                  </td>
                  <td className="mono" style={{ textAlign: "right" }}>
                    {formatMetricValue(key, s.mean)}
                  </td>
                  <td className="mono" style={{ textAlign: "right" }}>
                    {formatMetricValue(key, s.median)}
                  </td>
                  <td className="mono" style={{ textAlign: "right" }}>
                    {s.p10 != null ? formatMetricValue(key, s.p10) : "—"}
                  </td>
                  <td className="mono" style={{ textAlign: "right" }}>
                    {s.p90 != null ? formatMetricValue(key, s.p90) : "—"}
                  </td>
                  {showWinRate ? (
                    <td className="mono" style={{ textAlign: "right" }}>
                      {fmtPct(s.win_rate)}
                    </td>
                  ) : null}
                  <td className="mono muted" style={{ textAlign: "right" }}>
                    {s.n_valid ?? 0}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** 事件统计任务详情 */
export function EventStatsRunPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [eventPage, setEventPage] = useState(1); // 1-based
  const [eventPageSize, setEventPageSize] = useState(20);

  const patterns = useQuery({ queryKey: ["patterns-meta"], queryFn: api.patternsMeta });

  const run = useQuery({
    queryKey: ["event-stats-run", runId],
    queryFn: () => api.eventStatsRunDetail(runId),
    enabled: !!runId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "PENDING" || s === "RUNNING" ? 500 : false;
    },
  });

  const events = useQuery({
    queryKey: ["event-stats-events", runId, eventPage, eventPageSize],
    queryFn: () =>
      api.eventStatsEvents(runId, {
        limit: eventPageSize,
        offset: (eventPage - 1) * eventPageSize,
        order_by: "return_10",
        desc: true,
      }),
    enabled: !!runId && run.data?.status === "SUCCESS",
  });

  const chartEvents = useQuery({
    queryKey: ["event-stats-events-chart", runId],
    queryFn: () =>
      api.eventStatsEvents(runId, { limit: 500, order_by: "return_10", desc: true }),
    enabled: !!runId && run.data?.status === "SUCCESS",
  });

  const rerunMut = useMutation({
    mutationFn: () =>
      api.eventStatsRun(buildRerunBody(run.data!, { day: 6, match: 8, observe: 8 })),
    onSuccess: (j) => {
      void qc.invalidateQueries({ queryKey: ["event-stats-runs"] });
      navigate(`/event-stats?job=${j.job_id}`);
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => api.deleteEventStatsRun(runId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["event-stats-runs"] });
      navigate("/event-stats");
    },
  });

  const cancelMut = useMutation({
    mutationFn: () => api.cancelEventStatsRun(runId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["event-stats-run", runId] });
      void qc.invalidateQueries({ queryKey: ["event-stats-runs"] });
    },
  });

  const summary = run.data?.summary as Record<string, unknown> | null | undefined;
  const coverage = (summary?.coverage || {}) as Record<string, unknown>;
  const isActive = run.data?.status === "PENDING" || run.data?.status === "RUNNING";
  const narrative = useMemo(() => buildRunNarrative(summary), [summary]);

  if (!runId) {
    return <p className="muted">缺少任务 ID</p>;
  }

  if (run.isError) {
    return (
      <div>
        <Link to="/event-stats">← 返回列表</Link>
        <div className="error-box" style={{ marginTop: "0.75rem" }}>
          {(run.error as Error).message}
        </div>
      </div>
    );
  }

  if (run.isLoading || !run.data) {
    return <p className="muted">加载任务…</p>;
  }

  const r = run.data;
  const jobAlive = r.job_alive === true;

  return (
    <>
      <div className="page-head" style={{ alignItems: "flex-start" }}>
        <div>
          <p style={{ margin: "0 0 0.35rem" }}>
            <Link to="/event-stats" className="muted">
              ← 返回列表
            </Link>
          </p>
          <h1 style={{ marginBottom: "0.25rem" }}>
            任务 <span className="mono">{r.run_id.slice(0, 10)}</span>
            <span
              className={`badge ${
                r.status === "SUCCESS"
                  ? "ok"
                  : r.status === "FAILED" || r.status === "CANCELLED"
                    ? "fail"
                    : "warn"
              }`}
              style={{ marginLeft: "0.5rem", verticalAlign: "middle" }}
            >
              {STATUS_LABELS[r.status] || r.status}
            </span>
          </h1>
          <p className="muted" style={{ margin: 0, fontSize: "0.88rem" }}>
            {patternLabel(
              r.entry_pattern_id,
              patterns.data?.find((p) => p.id === r.entry_pattern_id),
            )}{" "}
            · <span className="mono">{r.entry_pattern_id}</span> v{r.entry_version} · 观测窗{" "}
            {r.horizon_bars} 日 · {formatUniverseSpec(r.universe_spec)} · {r.start_date} →{" "}
            {r.end_date}
          </p>
        </div>
        <div className="es-actions">
          {isActive && (
            <button
              type="button"
              className="btn"
              disabled={cancelMut.isPending}
              onClick={() => {
                if (!window.confirm("确认取消该任务？")) return;
                cancelMut.mutate();
              }}
            >
              取消
            </button>
          )}
          {r.status === "SUCCESS" && (
            <button
              type="button"
              className="btn"
              onClick={() => navigate(buildCompareHrefWithAdd(r.run_id))}
            >
              加入对比
            </button>
          )}
          <button
            type="button"
            className="btn"
            disabled={isActive || rerunMut.isPending}
            onClick={() => {
              if (!window.confirm("按此配置重新执行并返回列表？")) return;
              rerunMut.mutate();
            }}
          >
            重跑
          </button>
          <button
            type="button"
            className="btn"
            disabled={jobAlive || deleteMut.isPending}
            onClick={() => {
              if (!window.confirm("确认删除本任务及全部事件？不可恢复。")) return;
              deleteMut.mutate();
            }}
          >
            删除
          </button>
        </div>
      </div>

      {(rerunMut.error || deleteMut.error || cancelMut.error) && (
        <div className="error-box">
          {(rerunMut.error as Error)?.message ||
            (deleteMut.error as Error)?.message ||
            (cancelMut.error as Error)?.message}
        </div>
      )}

      {isActive && (
        <JobProgress
          jobId={r.job_id || r.run_id}
          job={r.live_job || runToProgressJob(r)}
          title="运行进度"
          cancellable={jobAlive || r.job_alive !== false}
          configSummary={formatJobParams({
            pattern_id: r.entry_pattern_id,
            start: r.start_date,
            end: r.end_date,
            universe: r.universe_spec,
            horizon_bars: r.horizon_bars,
          })}
          hint={
            r.job_alive === false
              ? "后台进程已丢失。可点取消清理，或返回列表删除。"
              : undefined
          }
          onCancelRequest={() => api.cancelEventStatsRun(runId)}
          onCancelled={() => {
            void qc.invalidateQueries({ queryKey: ["event-stats-run", runId] });
          }}
        />
      )}

      {r.status === "SUCCESS" && summary && (
        <>
          <p className="es-narrative">{narrative}</p>

          <div className="cards" style={{ marginBottom: "0.85rem" }}>
            <div className="card">
              <div className="label">事件 / 股票</div>
              <div className="value mono">
                {String(coverage.event_count ?? "—")} / {String(coverage.stock_count ?? "—")}
              </div>
            </div>
            {(
              [
                ["return_1", "1 日"],
                ["return_3", "3 日"],
                ["return_5", "5 日"],
                ["return_10", "10 日"],
              ] as const
            ).map(([key, label]) => {
              const st = statsOf(summary, key);
              return (
                <div className="card" key={key}>
                  <div className="label">{label}均 / 中位 / 胜率</div>
                  <div className="value mono" style={{ fontSize: "0.98rem" }}>
                    {formatMetricValue(key, st.mean)}
                    <span className="muted" style={{ fontWeight: 400 }}>
                      {" "}
                      / {formatMetricValue(key, st.median)}
                    </span>
                    <span className="muted" style={{ fontWeight: 400, marginLeft: "0.35rem" }}>
                      · {fmtPct(st.win_rate)}
                    </span>
                  </div>
                </div>
              );
            })}
            <div className="card">
              <div className="label">平均 MAE</div>
              <div className="value mono">
                {formatMetricValue("mae", statsOf(summary, "mae").mean)}
              </div>
            </div>
          </div>

          <details className="es-fold">
            <summary>完整配置</summary>
            <div className="es-fold-body" style={{ padding: "0.75rem 1rem" }}>
              <p className="muted" style={{ margin: 0, fontSize: "0.85rem", lineHeight: 1.6 }}>
                去重 {r.dedup_policy || "—"} · 日历 {r.calendar || "—"} · 引擎配置{" "}
                <span className="mono">{r.engine_config_hash?.slice(0, 12) || "—"}</span>
                <br />
                宇宙 {formatUniverseSpec(r.universe_spec)}
                {r.error_msg ? (
                  <>
                    <br />
                    备注 {r.error_msg}
                  </>
                ) : null}
              </p>
            </div>
          </details>

          <RunDetailCharts summary={summary} events={chartEvents.data?.events || []} />

          <details className="es-fold">
            <summary>聚合数据表（核对数字）</summary>
            <div className="es-fold-body">
              <p className="muted" style={{ padding: "0 1rem", fontSize: "0.8rem" }}>
                中位数：样本排序后正中位置，比均值更抗极端值。P10 / P90：第 10% / 90% 分位，中间约 80% 落在两者之间。
              </p>
              <StatsTable title="远期收益" keys={RETURN_KEYS} summary={summary} showWinRate />
              <StatsTable title="路径与风险" keys={PATH_KEYS} summary={summary} />
              <StatsTable title="时间结构" keys={TIME_KEYS} summary={summary} />
            </div>
          </details>

          <details className="es-fold" open>
            <summary>
              事件明细
              <span className="muted" style={{ fontWeight: 400 }}>
                {" "}
                · 共 {events.data?.total ?? 0} 条（按 10 日收益）
              </span>
            </summary>
            <div className="es-fold-body">
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>代码</th>
                      <th>信号日</th>
                      <th>相似度</th>
                      <th>1日</th>
                      <th>3日</th>
                      <th>5日</th>
                      <th>10日</th>
                      <th>MFE</th>
                      <th>MAE</th>
                      <th>质量</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(events.data?.events || []).map((e) => (
                      <tr key={e.event_id}>
                        <td>
                          <Link to={`/stocks/${e.code}?date=${e.signal_date}`}>
                            <span className="mono">{e.code}</span>
                          </Link>
                        </td>
                        <td className="mono">{e.signal_date}</td>
                        <td className="mono">{e.entry_similarity?.toFixed(1)}</td>
                        <td className="mono">{fmtPct(e.return_1)}</td>
                        <td className="mono">{fmtPct(e.return_3)}</td>
                        <td className="mono">{fmtPct(e.return_5)}</td>
                        <td className="mono">{fmtPct(e.return_10)}</td>
                        <td className="mono">{fmtPct(e.mfe)}</td>
                        <td className="mono">{fmtPct(e.mae)}</td>
                        <td className="muted">
                          {STATUS_LABELS[e.forward_status] || e.forward_status}
                        </td>
                      </tr>
                    ))}
                    {!events.data?.events?.length && (
                      <tr>
                        <td colSpan={10} className="muted">
                          无事件
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <Pager
                page={eventPage}
                pageSize={eventPageSize}
                total={events.data?.total ?? 0}
                pageSizeOptions={[10, 20, 50, 100]}
                onPageChange={setEventPage}
                onPageSizeChange={(size) => {
                  setEventPageSize(size);
                  setEventPage(1);
                }}
              />
            </div>
          </details>
        </>
      )}

      {(r.status === "FAILED" || r.status === "CANCELLED") && (
        <div className="panel" style={{ padding: "1rem" }}>
          <p className="muted" style={{ margin: 0 }}>
            任务未产生完整统计。
            {r.error_msg ? (
              <>
                <br />
                <span className="mono">{r.error_msg}</span>
              </>
            ) : null}
          </p>
        </div>
      )}
    </>
  );
}
