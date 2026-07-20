import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueries, useQuery } from "@tanstack/react-query";
import { api, type EventStatsRun } from "@/api/client";
import { CompareCharts } from "@/components/eventstats/CompareCharts";
import { Pager } from "@/components/Pager";
import {
  MAX_COMPARE_RUNS,
  MIN_COMPARE_RUNS,
  compareColor,
  parseCompareIds,
  runCompareLabel,
  runCompareSubtitle,
  runCompareTitle,
  saveStoredCompareIds,
} from "@/lib/eventStatsCompare";
import {
  METRIC_LABELS,
  PATH_KEYS,
  RETURN_KEYS,
  TIME_KEYS,
  formatMetricValue,
  formatUniverseSpec,
  fmtPct,
  statsOf,
} from "@/lib/eventStatsLabels";
import {
  buildPatternMetaMap,
  lookupPatternMeta,
  patternLabel,
} from "@/lib/patternLabels";

/** 多任务对比：选 2～5 个 SUCCESS run，同页表+图对比 */
export function EventStatsComparePage() {
  const [params, setParams] = useSearchParams();
  const selectedIds = useMemo(() => parseCompareIds(params.get("ids")), [params]);
  const [pickerPage, setPickerPage] = useState(1);
  const [pickerPageSize, setPickerPageSize] = useState(10);

  useEffect(() => {
    saveStoredCompareIds(selectedIds);
  }, [selectedIds]);

  const setSelectedIds = (ids: string[]) => {
    const cleaned = parseCompareIds(ids.join(","));
    saveStoredCompareIds(cleaned);
    setParams(
      () => {
        const next = new URLSearchParams();
        if (cleaned.length) next.set("ids", cleaned.join(","));
        return next;
      },
      { replace: true },
    );
  };

  const toggleId = (id: string) => {
    if (selectedIds.includes(id)) {
      setSelectedIds(selectedIds.filter((x) => x !== id));
      return;
    }
    if (selectedIds.length >= MAX_COMPARE_RUNS) return;
    setSelectedIds([...selectedIds, id]);
  };

  const patterns = useQuery({ queryKey: ["patterns-meta"], queryFn: api.patternsMeta });
  const patternMetaMap = useMemo(
    () => buildPatternMetaMap(patterns.data),
    [patterns.data],
  );

  const listQ = useQuery({
    queryKey: ["event-stats-runs", "compare-picker", pickerPage, pickerPageSize],
    queryFn: () => api.eventStatsRuns(pickerPageSize, (pickerPage - 1) * pickerPageSize),
  });

  const detailQueries = useQueries({
    queries: selectedIds.map((id) => ({
      queryKey: ["event-stats-run", id],
      queryFn: () => api.eventStatsRunDetail(id),
      staleTime: 30_000,
    })),
  });

  const selectedRuns = useMemo(() => {
    const map = new Map<string, EventStatsRun>();
    detailQueries.forEach((q) => {
      if (q.data) map.set(q.data.run_id, q.data);
    });
    return selectedIds.map((id) => map.get(id)).filter((r): r is EventStatsRun => !!r);
  }, [detailQueries, selectedIds]);

  const successRuns = useMemo(
    () => selectedRuns.filter((r) => r.status === "SUCCESS" && r.summary),
    [selectedRuns],
  );

  const eventQueries = useQueries({
    queries: successRuns.map((r) => ({
      queryKey: ["event-stats-events-chart", r.run_id],
      queryFn: () =>
        api.eventStatsEvents(r.run_id, { limit: 500, order_by: "return_10", desc: true }),
      staleTime: 60_000,
      enabled: successRuns.length >= MIN_COMPARE_RUNS,
    })),
  });

  const eventsByRunId = useMemo(() => {
    const out: Record<string, import("@/api/client").EventStatsEvent[]> = {};
    successRuns.forEach((r, i) => {
      out[r.run_id] = eventQueries[i]?.data?.events || [];
    });
    return out;
  }, [successRuns, eventQueries]);

  const detailsLoading = detailQueries.some((q) => q.isLoading);
  const detailsError = detailQueries.find((q) => q.isError)?.error as Error | undefined;
  const missingIds = selectedIds.filter((_, i) => {
    const q = detailQueries[i];
    return q && !q.isLoading && !q.data && !q.isError;
  });
  const failedIds = selectedIds.filter((_, i) => {
    const r = detailQueries[i]?.data;
    return r && r.status !== "SUCCESS";
  });

  const canCompare = successRuns.length >= MIN_COMPARE_RUNS;

  return (
    <>
      <div className="page-head">
        <div>
          <p style={{ margin: "0 0 0.35rem" }}>
            <Link to="/event-stats" className="muted">
              ← 返回列表
            </Link>
          </p>
          <h1>任务对比</h1>
          <p className="muted">
            选择 2～{MAX_COMPARE_RUNS} 个已成功任务，同页对比配置、指标与图表（URL 可分享）
          </p>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: "0.85rem" }}>
        <div className="panel-head">已选任务（{selectedIds.length}/{MAX_COMPARE_RUNS}）</div>
        <div className="es-compare-chips">
          {selectedIds.length === 0 && (
            <p className="muted" style={{ margin: 0 }}>
              尚未选择。在下方列表勾选成功任务。
            </p>
          )}
          {selectedIds.map((id, i) => {
            const run = selectedRuns.find((r) => r.run_id === id);
            const color = compareColor(i);
            return (
              <div key={id} className="es-compare-chip" style={{ borderColor: color }}>
                <span className="es-compare-dot" style={{ background: color }} />
                <div className="es-compare-chip-body">
                  <div className="mono" style={{ fontWeight: 600 }}>
                    {run ? runCompareLabel(run, i) : id.slice(0, 8)}
                  </div>
                  <div className="muted" style={{ fontSize: "0.78rem" }}>
                    {run
                      ? runCompareTitle(
                          run,
                          lookupPatternMeta(patternMetaMap, run.entry_pattern_id),
                        )
                      : detailsLoading
                        ? "加载中…"
                        : "未找到"}
                  </div>
                </div>
                <button
                  type="button"
                  className="btn"
                  style={{ padding: "0.2rem 0.45rem", fontSize: "0.8rem" }}
                  onClick={() => toggleId(id)}
                >
                  移除
                </button>
              </div>
            );
          })}
        </div>
        {selectedIds.length > 0 && selectedIds.length < MIN_COMPARE_RUNS && (
          <p className="muted" style={{ padding: "0 1rem 0.75rem", margin: 0, fontSize: "0.85rem" }}>
            至少再选 {MIN_COMPARE_RUNS - selectedIds.length} 个任务以开始对比
          </p>
        )}
        {failedIds.length > 0 && (
          <p className="error-box" style={{ margin: "0 1rem 0.75rem" }}>
            以下任务非成功状态，不参与图表：{failedIds.map((id) => id.slice(0, 8)).join(", ")}
          </p>
        )}
        {detailsError && (
          <div className="error-box" style={{ margin: "0 1rem 0.75rem" }}>
            {detailsError.message}
          </div>
        )}
      </div>

      <div className="panel" style={{ marginBottom: "0.85rem" }}>
        <div className="panel-head">从历史任务中选择</div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th style={{ width: 48 }}>选</th>
                <th>任务</th>
                <th>策略</th>
                <th>区间</th>
                <th>宇宙</th>
                <th>状态</th>
                <th style={{ textAlign: "right" }}>事件</th>
              </tr>
            </thead>
            <tbody>
              {(listQ.data?.runs || []).map((r) => {
                const checked = selectedIds.includes(r.run_id);
                const disabled =
                  r.status !== "SUCCESS" ||
                  (!checked && selectedIds.length >= MAX_COMPARE_RUNS);
                return (
                  <tr key={r.run_id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={disabled}
                        onChange={() => toggleId(r.run_id)}
                        title={
                          r.status !== "SUCCESS"
                            ? "仅可对比成功任务"
                            : !checked && selectedIds.length >= MAX_COMPARE_RUNS
                              ? `最多 ${MAX_COMPARE_RUNS} 个`
                              : undefined
                        }
                      />
                    </td>
                    <td>
                      <Link to={`/event-stats/runs/${r.run_id}`} className="mono">
                        {r.run_id.slice(0, 10)}
                      </Link>
                    </td>
                    <td>
                      {patternLabel(
                        r.entry_pattern_id,
                        lookupPatternMeta(patternMetaMap, r.entry_pattern_id),
                      )}
                    </td>
                    <td className="mono" style={{ fontSize: "0.82rem" }}>
                      {r.start_date} → {r.end_date}
                    </td>
                    <td className="muted" style={{ fontSize: "0.82rem" }}>
                      {formatUniverseSpec(r.universe_spec)}
                    </td>
                    <td>{r.status === "SUCCESS" ? "成功" : r.status}</td>
                    <td className="mono" style={{ textAlign: "right" }}>
                      {r.event_count ?? "—"}
                    </td>
                  </tr>
                );
              })}
              {!listQ.data?.runs?.length && !listQ.isLoading && (
                <tr>
                  <td colSpan={7} className="muted">
                    暂无任务
                  </td>
                </tr>
              )}
              {listQ.isLoading && (
                <tr>
                  <td colSpan={7} className="muted">
                    加载中…
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <Pager
          page={pickerPage}
          pageSize={pickerPageSize}
          total={listQ.data?.total ?? 0}
          pageSizeOptions={[10, 20, 50]}
          onPageChange={setPickerPage}
          onPageSizeChange={(size) => {
            setPickerPageSize(size);
            setPickerPage(1);
          }}
        />
      </div>

      {canCompare && (
        <>
          <ConfigCompareTable runs={successRuns} patternMetaMap={patternMetaMap} />
          <MetricsCompareTable runs={successRuns} patternMetaMap={patternMetaMap} />
          <CompareCharts runs={successRuns} eventsByRunId={eventsByRunId} />
        </>
      )}

      {!canCompare && selectedIds.length >= MIN_COMPARE_RUNS && detailsLoading && (
        <p className="muted">加载任务详情…</p>
      )}

      {missingIds.length > 0 && (
        <p className="muted">部分 ID 无效：{missingIds.join(", ")}</p>
      )}
    </>
  );
}

function ConfigCompareTable({
  runs,
  patternMetaMap,
}: {
  runs: EventStatsRun[];
  patternMetaMap: ReturnType<typeof buildPatternMetaMap>;
}) {
  const rows: Array<{ label: string; values: string[] }> = [
    {
      label: "任务",
      values: runs.map((r, i) => runCompareLabel(r, i)),
    },
    {
      label: "策略",
      values: runs.map((r) => {
        const meta = lookupPatternMeta(patternMetaMap, r.entry_pattern_id);
        return `${patternLabel(r.entry_pattern_id, meta)} · ${r.entry_pattern_id} v${r.entry_version}`;
      }),
    },
    {
      label: "区间",
      values: runs.map((r) => `${r.start_date} → ${r.end_date}`),
    },
    {
      label: "宇宙",
      values: runs.map((r) => formatUniverseSpec(r.universe_spec)),
    },
    {
      label: "观测窗",
      values: runs.map((r) => `${r.horizon_bars} 日`),
    },
    {
      label: "事件 / 股票",
      values: runs.map((r) => {
        const cov = (r.summary?.coverage || {}) as Record<string, unknown>;
        return `${cov.event_count ?? r.event_count ?? "—"} / ${cov.stock_count ?? "—"}`;
      }),
    },
    {
      label: "摘要",
      values: runs.map((r) => runCompareSubtitle(r)),
    },
  ];

  return (
    <div className="panel" style={{ marginBottom: "0.85rem" }}>
      <div className="panel-head">配置对照</div>
      <div className="table-wrap">
        <table className="data es-compare-table">
          <thead>
            <tr>
              <th>项</th>
              {runs.map((r, i) => (
                <th key={r.run_id}>
                  <span className="es-compare-dot" style={{ background: compareColor(i) }} />
                  <Link to={`/event-stats/runs/${r.run_id}`} className="mono">
                    {runCompareLabel(r, i)}
                  </Link>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(1).map((row) => (
              <tr key={row.label}>
                <td className="muted">{row.label}</td>
                {row.values.map((v, i) => (
                  <td key={runs[i].run_id} style={{ fontSize: "0.85rem" }}>
                    {v}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MetricsCompareTable({
  runs,
  patternMetaMap,
}: {
  runs: EventStatsRun[];
  patternMetaMap: ReturnType<typeof buildPatternMetaMap>;
}) {
  return (
    <div className="panel" style={{ marginBottom: "0.85rem" }}>
      <div className="panel-head">指标对比</div>
      <MetricBlock
        title="远期收益"
        keys={RETURN_KEYS}
        runs={runs}
        patternMetaMap={patternMetaMap}
        showWinRate
      />
      <details className="es-fold">
        <summary>路径与风险</summary>
        <div className="es-fold-body">
          <MetricBlock title="" keys={PATH_KEYS} runs={runs} patternMetaMap={patternMetaMap} />
        </div>
      </details>
      <details className="es-fold">
        <summary>时间结构</summary>
        <div className="es-fold-body">
          <MetricBlock title="" keys={TIME_KEYS} runs={runs} patternMetaMap={patternMetaMap} />
        </div>
      </details>
    </div>
  );
}

function MetricBlock({
  title,
  keys,
  runs,
  patternMetaMap,
  showWinRate,
}: {
  title: string;
  keys: readonly string[];
  runs: EventStatsRun[];
  patternMetaMap: ReturnType<typeof buildPatternMetaMap>;
  showWinRate?: boolean;
}) {
  return (
    <div style={{ marginBottom: title ? "0.5rem" : 0 }}>
      {title ? (
        <div className="panel-head" style={{ border: "none", padding: "0.5rem 1rem" }}>
          {title}
          <span className="muted" style={{ fontWeight: 400, marginLeft: "0.5rem", fontSize: "0.8rem" }}>
            每列一个任务，横向对比
          </span>
        </div>
      ) : null}
      <div className="table-wrap">
        <table className="data es-compare-table">
          <thead>
            <tr>
              <th style={{ minWidth: 120 }}>指标</th>
              {runs.map((r, i) => (
                <th
                  key={r.run_id}
                  className="es-compare-run-col"
                  style={{ borderTop: `3px solid ${compareColor(i)}` }}
                >
                  <span className="es-compare-dot" style={{ background: compareColor(i) }} />
                  <Link to={`/event-stats/runs/${r.run_id}`} className="mono">
                    {runCompareLabel(r, i)}
                  </Link>
                  <div className="muted" style={{ fontWeight: 400, fontSize: "0.72rem", marginTop: 2 }}>
                    {patternLabel(
                      r.entry_pattern_id,
                      lookupPatternMeta(patternMetaMap, r.entry_pattern_id),
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => (
              <tr key={key}>
                <td>{METRIC_LABELS[key] || key}</td>
                {runs.map((r, i) => {
                  const s = statsOf(r.summary as Record<string, unknown>, key);
                  return (
                    <td key={r.run_id} className="es-compare-metric-cell">
                      <div className="es-compare-metric-stack">
                        <div>
                          <span className="es-compare-metric-k">均</span>
                          <span className="mono">{formatMetricValue(key, s.mean)}</span>
                        </div>
                        <div>
                          <span className="es-compare-metric-k">中</span>
                          <span className="mono">{formatMetricValue(key, s.median)}</span>
                        </div>
                        {showWinRate ? (
                          <div>
                            <span className="es-compare-metric-k">胜</span>
                            <span className="mono">{fmtPct(s.win_rate)}</span>
                          </div>
                        ) : null}
                      </div>
                      <span
                        className="es-compare-col-tint"
                        style={{ background: compareColor(i) }}
                        aria-hidden
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
